// Two Static Web Apps (ADR-004): PWA coordinador and web admin, served behind Front Door.

param env string
param tags object
@description('Static Web Apps region (limited set). Not necessarily the main location.')
param swaLocation string = 'eastus2'
@description('Standard is required for private endpoints and enterprise-grade edge; Free for dev only.')
@allowed(['Free', 'Standard'])
param sku string = 'Standard'

var apps = [
  { key: 'pwa', name: 'swa-pipeline-pwa-${env}' }
  { key: 'admin', name: 'swa-pipeline-admin-${env}' }
]

resource sites 'Microsoft.Web/staticSites@2023-01-01' = [
  for app in apps: {
    name: app.name
    location: swaLocation
    tags: tags
    sku: { name: sku, tier: sku }
    properties: {
      stagingEnvironmentPolicy: 'Disabled'
      allowConfigFileUpdates: true
      enterpriseGradeCdnStatus: 'Disabled'
    }
  }
]

output pwaName string = sites[0].name
output pwaDefaultHostname string = sites[0].properties.defaultHostname
output adminName string = sites[1].name
output adminDefaultHostname string = sites[1].properties.defaultHostname
