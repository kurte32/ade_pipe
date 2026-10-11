// Two storage accounts (ADR-003):
//   staging:   flat Blob, Defender for Storage on-upload malware scanning (results as blob index tags),
//              lifecycle rule removes abandoned uploads after 7 days.
//   documents: ADLS Gen2 (hierarchical namespace) exposed to Fabric through a OneLake shortcut,
//              container-level time-based immutability (5 years) and legal hold capability.
// Both: shared key disabled, TLS 1.2, public network access disabled, private endpoints,
// managed identity access only.

param location string
param env string
param tags object
param peSubnetId string
param blobDnsZoneId string
param dfsDnsZoneId string
param apiIdentityPrincipalId string
param privateNetworking bool = true
@description('Allow trusted Azure services (Defender for Storage, Fabric trusted workspace access) through the firewall.')
param allowTrustedAzureServices bool = true
@description('Enable Defender for Storage on-upload malware scanning on the staging account (requires the Defender plan).')
param enableDefenderScanning bool = true
@description('Log Analytics workspace for blob read/write/delete logs on both accounts (audit INF-4).')
param workspaceId string = ''
param defenderCapGbPerMonth int = 1000
@description('Time-based immutability period for the documents container in days. 0 disables the policy (dev).')
param documentsImmutabilityDays int = 1826
@description('Lock the immutability policy. Locked policies cannot be shortened or removed. Production only.')
param lockImmutabilityPolicy bool = false
@description('Fabric workspace identity object id for trusted workspace access via resource instance rules. Empty to skip.')
param fabricWorkspaceIdentityPrincipalId string = ''

var stagingName = toLower('st${env}pipelinestg')
var documentsName = toLower('st${env}pipelinedoc')
// Storage Blob Data Contributor, Storage Blob Data Reader
var blobContributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
var blobReaderRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1')

var commonProps = {
  minimumTlsVersion: 'TLS1_2'
  supportsHttpsTrafficOnly: true
  allowBlobPublicAccess: false
  allowSharedKeyAccess: false
  defaultToOAuthAuthentication: true
  allowCrossTenantReplication: false
  publicNetworkAccess: privateNetworking ? 'Disabled' : 'Enabled'
  networkAcls: {
    defaultAction: privateNetworking ? 'Deny' : 'Allow'
    bypass: allowTrustedAzureServices ? 'AzureServices' : 'None'
  }
  encryption: {
    keySource: 'Microsoft.Storage'
    requireInfrastructureEncryption: false
    services: {
      blob: { enabled: true, keyType: 'Account' }
    }
  }
}

resource staging 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: stagingName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_ZRS' }
  properties: union(commonProps, {
    isHnsEnabled: false
    accessTier: 'Hot'
  })
}

resource stagingBlob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: staging
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 7 }
    containerDeleteRetentionPolicy: { enabled: true, days: 7 }
    isVersioningEnabled: false
  }
}

resource stagingContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: stagingBlob
  name: 'staging'
  properties: { publicAccess: 'None' }
}

resource stagingLifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: staging
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'delete-abandoned-uploads'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: ['blockBlob']
              prefixMatch: ['staging/subidas/']
            }
            actions: {
              baseBlob: { delete: { daysAfterModificationGreaterThan: 7 } }
            }
          }
        }
      ]
    }
  }
}

// Defender for Storage: on-upload malware scanning writes 'Malware Scanning scan result' index tags
// and publishes Event Grid events. Index tags are only available on flat-namespace accounts.
resource stagingDefender 'Microsoft.Security/defenderForStorageSettings@2022-12-01-preview' = if (enableDefenderScanning) {
  name: 'current'
  scope: staging
  properties: {
    isEnabled: true
    overrideSubscriptionLevelSettings: true
    malwareScanning: {
      onUpload: {
        isEnabled: true
        capGBPerMonth: defenderCapGbPerMonth
      }
    }
    sensitiveDataDiscovery: { isEnabled: false }
  }
}

resource documents 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: documentsName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_GZRS' }
  properties: union(commonProps, {
    isHnsEnabled: true
    accessTier: 'Hot'
  })
}

resource documentsBlob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: documents
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 30 }
    containerDeleteRetentionPolicy: { enabled: true, days: 30 }
  }
}

resource documentsBlobDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(workspaceId)) {
  name: 'documents-blob-to-log-analytics'
  scope: documentsBlob
  properties: {
    workspaceId: workspaceId
    logs: [
      { category: 'StorageRead', enabled: true }
      { category: 'StorageWrite', enabled: true }
      { category: 'StorageDelete', enabled: true }
    ]
  }
}

resource stagingBlobDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(workspaceId)) {
  name: 'staging-blob-to-log-analytics'
  scope: stagingBlob
  properties: {
    workspaceId: workspaceId
    logs: [
      { category: 'StorageWrite', enabled: true }
      { category: 'StorageDelete', enabled: true }
    ]
  }
}

resource documentsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: documentsBlob
  name: 'documents'
  properties: { publicAccess: 'None' }
}

// Container-level time-based retention (WORM). Legal holds are applied on demand with
// `az storage container legal-hold set` (documented in AZURE_DEPLOYMENT.md). Retention start event
// is TDD pendiente 7; the period is a parameter so the policy can follow Legal's answer.
resource documentsImmutability 'Microsoft.Storage/storageAccounts/blobServices/containers/immutabilityPolicies@2023-05-01' = if (documentsImmutabilityDays > 0) {
  parent: documentsContainer
  name: 'default'
  properties: {
    immutabilityPeriodSinceCreationInDays: documentsImmutabilityDays
    allowProtectedAppendWrites: false
  }
}

// Fabric trusted workspace access: a resource instance rule is not expressible for Fabric workspaces in
// Bicep today; the role assignment below grants the workspace identity read access and the network rule is
// documented as a manual step (AZURE_DEPLOYMENT.md). Verify in the tenant (TO_BE.md open 3).
resource fabricReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(fabricWorkspaceIdentityPrincipalId)) {
  name: guid(documents.id, fabricWorkspaceIdentityPrincipalId, blobReaderRoleId)
  scope: documents
  properties: {
    roleDefinitionId: blobReaderRoleId
    principalId: fabricWorkspaceIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource apiStagingContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(staging.id, apiIdentityPrincipalId, blobContributorRoleId)
  scope: staging
  properties: {
    roleDefinitionId: blobContributorRoleId
    principalId: apiIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource apiDocumentsContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(documents.id, apiIdentityPrincipalId, blobContributorRoleId)
  scope: documents
  properties: {
    roleDefinitionId: blobContributorRoleId
    principalId: apiIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Private endpoints: blob for both accounts, dfs for the documents account (Fabric shortcut and tooling).
var endpoints = privateNetworking
  ? [
      { name: 'pe-${stagingName}-blob', accountId: staging.id, group: 'blob', zone: blobDnsZoneId }
      { name: 'pe-${documentsName}-blob', accountId: documents.id, group: 'blob', zone: blobDnsZoneId }
      { name: 'pe-${documentsName}-dfs', accountId: documents.id, group: 'dfs', zone: dfsDnsZoneId }
    ]
  : []

resource pes 'Microsoft.Network/privateEndpoints@2023-11-01' = [
  for e in endpoints: {
    name: e.name
    location: location
    tags: tags
    properties: {
      subnet: { id: peSubnetId }
      privateLinkServiceConnections: [
        {
          name: e.group
          properties: {
            privateLinkServiceId: e.accountId
            groupIds: [e.group]
          }
        }
      ]
    }
  }
]

resource peDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = [
  for (e, i) in endpoints: {
    parent: pes[i]
    name: 'default'
    properties: {
      privateDnsZoneConfigs: [
        {
          name: e.group
          properties: { privateDnsZoneId: e.zone }
        }
      ]
    }
  }
]

// Locking an immutability policy is a separate, irreversible API call (az storage container immutability-policy lock).
// The flag is surfaced so the deployment summary and AZURE_DEPLOYMENT.md step can act on it.
output immutabilityPolicyLockRequested bool = lockImmutabilityPolicy && documentsImmutabilityDays > 0
output stagingAccountName string = staging.name
output stagingBlobEndpoint string = staging.properties.primaryEndpoints.blob
output documentsAccountName string = documents.name
output documentsBlobEndpoint string = documents.properties.primaryEndpoints.blob
output documentsDfsEndpoint string = documents.properties.primaryEndpoints.dfs
output stagingAccountId string = staging.id
output documentsAccountId string = documents.id
