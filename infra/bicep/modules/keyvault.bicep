// Key Vault in RBAC mode with private endpoint (ADR-008). Holds the few non-identity settings the
// container app reads as Key Vault references. No application secrets exist: identity is managed.

param location string
param env string
param tags object
param peSubnetId string
param vaultDnsZoneId string
param apiIdentityPrincipalId string
@description('Principal id of the migration job identity; it reads the same App Insights KV secret.')
param migrationIdentityPrincipalId string
param privateNetworking bool = true
@secure()
param appInsightsConnectionString string

var kvName = 'kv-pipeline-${env}'
// Key Vault Secrets User
var secretsUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  tags: tags
  properties: {
    tenantId: tenant().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
    publicNetworkAccess: privateNetworking ? 'Disabled' : 'Enabled'
    networkAcls: {
      defaultAction: privateNetworking ? 'Deny' : 'Allow'
      bypass: 'AzureServices'
    }
  }
}

resource appInsightsSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'appinsights-connection-string'
  tags: tags
  properties: {
    value: appInsightsConnectionString
    contentType: 'text/plain'
  }
}

resource apiSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, apiIdentityPrincipalId, secretsUserRoleId)
  scope: vault
  properties: {
    roleDefinitionId: secretsUserRoleId
    principalId: apiIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// The migrate job is passed the App Insights KV secret under its own identity (containerapps.bicep),
// so it needs Secrets User too, or every environment's deploy fails at the migration step (audit D-02).
resource migrationSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, migrationIdentityPrincipalId, secretsUserRoleId)
  scope: vault
  properties: {
    roleDefinitionId: secretsUserRoleId
    principalId: migrationIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource pe 'Microsoft.Network/privateEndpoints@2023-11-01' = if (privateNetworking) {
  name: 'pe-${kvName}'
  location: location
  tags: tags
  properties: {
    subnet: { id: peSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'vault'
        properties: {
          privateLinkServiceId: vault.id
          groupIds: ['vault']
        }
      }
    ]
  }
}

resource peDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = if (privateNetworking) {
  parent: pe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'vault'
        properties: { privateDnsZoneId: vaultDnsZoneId }
      }
    ]
  }
}

output vaultId string = vault.id
output vaultName string = vault.name
output vaultUri string = vault.properties.vaultUri
output appInsightsSecretUri string = appInsightsSecret.properties.secretUri
