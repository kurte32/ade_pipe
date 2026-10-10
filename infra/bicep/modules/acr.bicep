// Azure Container Registry (ADR-010). Premium enables the private endpoint; Standard otherwise.

param location string
param env string
param tags object
param orgPrefix string
param peSubnetId string
param acrDnsZoneId string
param apiIdentityPrincipalId string
param migrationIdentityPrincipalId string
@allowed(['Standard', 'Premium'])
param sku string = 'Standard'
@description('Private endpoint and disabled public access. Requires Premium.')
param privateEndpoint bool = false

var acrName = toLower('cr${orgPrefix}pipeline${env}')
// AcrPull
var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
var usePrivate = privateEndpoint && sku == 'Premium'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  tags: tags
  sku: { name: sku }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: usePrivate ? 'Disabled' : 'Enabled'
    zoneRedundancy: sku == 'Premium' ? 'Enabled' : 'Disabled'
    networkRuleBypassOptions: 'AzureServices'
    policies: {
      quarantinePolicy: { status: 'disabled' }
      retentionPolicy: { status: sku == 'Premium' ? 'enabled' : 'disabled', days: 30 }
      trustPolicy: { status: 'disabled', type: 'Notary' }
    }
  }
}

resource apiPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, apiIdentityPrincipalId, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: apiIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource migrationPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, migrationIdentityPrincipalId, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: migrationIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource pe 'Microsoft.Network/privateEndpoints@2023-11-01' = if (usePrivate) {
  name: 'pe-${acrName}'
  location: location
  tags: tags
  properties: {
    subnet: { id: peSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'registry'
        properties: {
          privateLinkServiceId: acr.id
          groupIds: ['registry']
        }
      }
    ]
  }
}

resource peDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = if (usePrivate) {
  parent: pe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'registry'
        properties: { privateDnsZoneId: acrDnsZoneId }
      }
    ]
  }
}

output acrName string = acr.name
output loginServer string = acr.properties.loginServer
output acrId string = acr.id
