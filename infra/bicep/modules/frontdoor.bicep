// Front Door origin groups, origins and routes (profile, endpoints and WAF: frontdoor-profile.bicep).
// PWA host: /api/* -> Container Apps (Private Link origin), /* -> PWA SWA.
// Admin host: /api/* -> Container Apps, /* -> admin SWA.

param env string
param location string
@description('Deploy Front Door. Dev skips it and uses public ingress with IP restrictions.')
param enabled bool = true
param profileName string
param endpointName string
param adminEndpointName string
param pwaHostname string
param adminHostname string
param apiFqdn string
@description('Container Apps managed environment id for the Private Link origin.')
param managedEnvironmentId string

resource profile 'Microsoft.Cdn/profiles@2024-02-01' existing = if (enabled) {
  name: profileName
}

resource endpoint 'Microsoft.Cdn/profiles/afdEndpoints@2024-02-01' existing = if (enabled) {
  parent: profile
  name: endpointName
}

resource adminEndpoint 'Microsoft.Cdn/profiles/afdEndpoints@2024-02-01' existing = if (enabled) {
  parent: profile
  name: adminEndpointName
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
  { name: 'pwa', group: 0, patterns: ['/*'] }
]
var adminRoutes = [
  { name: 'api', group: 2, patterns: ['/api/*'] }
  { name: 'admin', group: 1, patterns: ['/*'] }
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

resource adminRouteResources 'Microsoft.Cdn/profiles/afdEndpoints/routes@2024-02-01' = [
  for r in adminRoutes: if (enabled) {
    parent: adminEndpoint
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
