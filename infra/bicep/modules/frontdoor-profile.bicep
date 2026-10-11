// Azure Front Door Premium profile, endpoints and WAF (AZURE_DESIGN.md section 3 zone 2).
// Split from the routes (frontdoor.bicep) so the profile id can reach the API before the API
// exists: the API validates X-Azure-FDID against it (backlog A3) and the routes need the API FQDN.

param env string
param tags object
@description('Deploy Front Door. Dev skips it and uses public ingress with IP restrictions.')
param enabled bool = true
@description('Rate limit threshold per client IP per minute.')
param rateLimitPerMinute int = 300
@allowed(['Detection', 'Prevention'])
param wafMode string = 'Prevention'
@description('Log Analytics workspace for access, WAF and health-probe logs (audit INF-4).')
param workspaceId string = ''

var profileName = 'afd-pipeline-${env}'
var endpointName = 'pipeline-${env}'
var adminEndpointName = 'pipeline-${env}-admin'
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

// Two endpoints (audit INF-1): the PWA host and the admin host. Host-based routing keeps both
// SPAs built with base '/', promotes one bundle unchanged and keeps MSAL's redirect URI = origin.
resource endpoint 'Microsoft.Cdn/profiles/afdEndpoints@2024-02-01' = if (enabled) {
  parent: profile
  name: endpointName
  location: 'global'
  tags: tags
  properties: { enabledState: 'Enabled' }
}

resource adminEndpoint 'Microsoft.Cdn/profiles/afdEndpoints@2024-02-01' = if (enabled) {
  parent: profile
  name: adminEndpointName
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
          domains: [{ id: endpoint.id }, { id: adminEndpoint.id }]
          patternsToMatch: ['/*']
        }
      ]
    }
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (enabled && !empty(workspaceId)) {
  name: 'frontdoor-to-log-analytics'
  scope: profile
  properties: {
    workspaceId: workspaceId
    logs: [
      { category: 'FrontDoorAccessLog', enabled: true }
      { category: 'FrontDoorWebApplicationFirewallLog', enabled: true }
      { category: 'FrontDoorHealthProbeLog', enabled: true }
    ]
  }
}

output profileName string = enabled ? profile!.name : ''
output endpointName string = enabled ? endpoint!.name : ''
output adminEndpointName string = enabled ? adminEndpoint!.name : ''
output endpointHostname string = enabled ? endpoint!.properties.hostName : ''
output adminEndpointHostname string = enabled ? adminEndpoint!.properties.hostName : ''
@description('Value of the X-Azure-FDID header Front Door adds; the API refuses /api/* requests without it.')
output frontDoorId string = enabled ? profile!.properties.frontDoorId : ''
