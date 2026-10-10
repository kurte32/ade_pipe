// Azure Front Door Premium with WAF (AZURE_DESIGN.md section 3 zone 2).
// Routes: /api/* -> Container Apps (Private Link origin), /admin/* -> admin SWA, /* -> PWA SWA.

param env string
param tags object
param location string
@description('Deploy Front Door. Dev skips it and uses public ingress with IP restrictions.')
param enabled bool = true
param pwaHostname string
param adminHostname string
param apiFqdn string
@description('Container Apps managed environment id for the Private Link origin.')
param managedEnvironmentId string
@description('Rate limit threshold per client IP per minute.')
param rateLimitPerMinute int = 300
@allowed(['Detection', 'Prevention'])
param wafMode string = 'Prevention'

var profileName = 'afd-pipeline-${env}'
var endpointName = 'pipeline-${env}'
var wafName = replace('wafpipeline${env}', '-', '')

resource profile 'Microsoft.Cdn/profiles@2024-02-01' = if (enabled) {
  name: profileName
  location: 'global'
  tags: tags
  sku: { name: 'Premium_AzureFrontDoor' }
  properties: {
    originResponseTimeoutSeconds: 240
  }
}

resource endpoint 'Microsoft.Cdn/profiles/afdEndpoints@2024-02-01' = if (enabled) {
  parent: profile
  name: endpointName
  location: 'global'
  tags: tags
  properties: { enabledState: 'Enabled' }
}

resource waf 'Microsoft.Network/FrontDoorWebApplicationFirewallPolicies@2024-02-01' = if (enabled) {
  name: wafName
  location: 'global'
  tags: tags
  sku: { name: 'Premium_AzureFrontDoor' }
  properties: {
    policySettings: {
      enabledState: 'Enabled'
      mode: wafMode
      requestBodyCheck: 'Enabled'
      customBlockResponseStatusCode: 403
    }
    managedRules: {
      managedRuleSets: [
        { ruleSetType: 'Microsoft_DefaultRuleSet', ruleSetVersion: '2.1', ruleSetAction: 'Block' }
        { ruleSetType: 'Microsoft_BotManagerRuleSet', ruleSetVersion: '1.0' }
      ]
    }
    customRules: {
      rules: [
        {
          name: 'RateLimitPerClient'
          priority: 100
          enabledState: 'Enabled'
          ruleType: 'RateLimitRule'
          rateLimitDurationInMinutes: 1
          rateLimitThreshold: rateLimitPerMinute
          action: 'Block'
          matchConditions: [
            {
              matchVariable: 'RequestUri'
              operator: 'Contains'
              matchValue: ['/']
            }
          ]
        }
      ]
    }
  }
}

resource securityPolicy 'Microsoft.Cdn/profiles/securityPolicies@2024-02-01' = if (enabled) {
  parent: profile
  name: 'waf'
  properties: {
    parameters: {
      type: 'WebApplicationFirewall'
      wafPolicy: { id: waf.id }
      associations: [
        {
          domains: [{ id: endpoint.id }]
          patternsToMatch: ['/*']
        }
      ]
    }
  }
}

var originGroups = [
  { name: 'og-pwa', probePath: '/', hostname: pwaHostname, privateLink: false }
  { name: 'og-admin', probePath: '/', hostname: adminHostname, privateLink: false }
  { name: 'og-api', probePath: '/healthz', hostname: apiFqdn, privateLink: true }
]

resource groups 'Microsoft.Cdn/profiles/originGroups@2024-02-01' = [
  for g in originGroups: if (enabled) {
    parent: profile
    name: g.name
    properties: {
      loadBalancingSettings: { sampleSize: 4, successfulSamplesRequired: 3, additionalLatencyInMilliseconds: 50 }
      healthProbeSettings: {
        probePath: g.probePath
        probeRequestType: 'GET'
        probeProtocol: 'Https'
        probeIntervalInSeconds: 60
      }
      sessionAffinityState: 'Disabled'
    }
  }
]

resource origins 'Microsoft.Cdn/profiles/originGroups/origins@2024-02-01' = [
  for (g, i) in originGroups: if (enabled) {
    parent: groups[i]
    name: 'origin'
    properties: {
      hostName: g.hostname
      originHostHeader: g.hostname
      httpPort: 80
      httpsPort: 443
      priority: 1
      weight: 1000
      enabledState: 'Enabled'
      enforceCertificateNameCheck: true
      sharedPrivateLinkResource: g.privateLink
        ? {
            privateLink: { id: managedEnvironmentId }
            groupId: 'managedEnvironments'
            privateLinkLocation: location
            requestMessage: 'Front Door origin for pipeline-api ${env}'
          }
        : null
    }
  }
]

var routes = [
  { name: 'api', group: 2, patterns: ['/api/*'] }
  { name: 'admin', group: 1, patterns: ['/admin', '/admin/*'] }
  { name: 'pwa', group: 0, patterns: ['/*'] }
]

resource routeResources 'Microsoft.Cdn/profiles/afdEndpoints/routes@2024-02-01' = [
  for r in routes: if (enabled) {
    parent: endpoint
    name: r.name
    properties: {
      originGroup: { id: groups[r.group].id }
      supportedProtocols: ['Https']
      patternsToMatch: r.patterns
      forwardingProtocol: 'HttpsOnly'
      linkToDefaultDomain: 'Enabled'
      httpsRedirect: 'Enabled'
      enabledState: 'Enabled'
      cacheConfiguration: null
    }
    dependsOn: [origins]
  }
]

output endpointHostname string = enabled ? endpoint!.properties.hostName : ''
output profileName string = enabled ? profile!.name : ''
