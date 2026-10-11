// Pipeline de Posibles Tiendas: resource-group scoped deployment composing all modules.
// Topology and choices: architecture/AZURE_DESIGN.md, ADR-001 to ADR-010.
// Create the resource group first with rg.bicep (subscription scope) or `az group create`.

targetScope = 'resourceGroup'

@allowed(['dev', 'test', 'prod'])
param env string
param location string = resourceGroup().location
param owner string = 'Subdireccion de Inteligencia Artificial'
@description('Short organisation prefix used in globally unique names (ACR).')
param orgPrefix string = 't3b'

// Network posture (ADR-008). false = service firewalls and public ingress with IP restrictions (dev).
param privateNetworking bool = true
param deployFrontDoor bool = true
param deployGatewaySubnet bool = true
param allowedIngressCidrs array = []

// Identity (Entra registrations created by the identity team, guide section 8 + ADR-006)
param authTenantId string
@description('pipeline-api application (client) id')
param authAudience string
@description('Comma-separated client ids of pipeline-pwa-coordinador and pipeline-web-admin')
param authAllowedAzp string
param sqlAdminGroupObjectId string
param sqlAdminGroupName string
param fabricWorkspaceIdentityPrincipalId string = ''
param teamsAppId string = ''

// Compute and data sizing
param apiImage string
param workloadProfileType string = 'D4'
param minReplicas int = 1
param maxReplicas int = 3
param zoneRedundant bool = true
param sqlSkuName string = 'GP_Gen5'
param sqlSkuTier string = 'GeneralPurpose'
param sqlSkuCapacity int = 2
param sqlAutoPauseDelayMinutes int = -1
param sqlMinCapacity string = ''
param sqlBackupStorageRedundancy string = 'GeoZone'
param acrSku string = 'Standard'
param acrPrivateEndpoint bool = false
param swaSku string = 'Standard'
param swaLocation string = 'eastus2'
param logDailyCapGb int = 1
param logRetentionDays int = 90

// Storage policy
param enableDefenderScanning bool = true
param documentsImmutabilityDays int = 1826
param lockImmutabilityPolicy bool = false

// Application
param environmentName string = 'production'
param logLevel string = 'INFO'
@description('Public URL of the PWA (Front Door host). Used in Teams notification links.')
param appPublicUrl string

var tags = {
  environment: env
  workload: 'pipeline-tiendas'
  owner: owner
}

module network 'modules/network.bicep' = {
  name: 'network-${env}'
  params: {
    location: location
    env: env
    tags: tags
    deployGatewaySubnet: deployGatewaySubnet && privateNetworking
  }
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring-${env}'
  params: {
    location: location
    env: env
    tags: tags
    dailyCapGb: logDailyCapGb
    retentionDays: logRetentionDays
  }
}

module identity 'modules/identity.bicep' = {
  name: 'identity-${env}'
  params: {
    location: location
    env: env
    tags: tags
  }
}

module keyvault 'modules/keyvault.bicep' = {
  name: 'keyvault-${env}'
  params: {
    location: location
    env: env
    tags: tags
    peSubnetId: network.outputs.peSubnetId
    vaultDnsZoneId: network.outputs.vaultDnsZoneId
    apiIdentityPrincipalId: identity.outputs.apiIdentityPrincipalId
    migrationIdentityPrincipalId: identity.outputs.migrationIdentityPrincipalId
    privateNetworking: privateNetworking
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
  }
}

module storage 'modules/storage.bicep' = {
  name: 'storage-${env}'
  params: {
    location: location
    env: env
    tags: tags
    peSubnetId: network.outputs.peSubnetId
    blobDnsZoneId: network.outputs.blobDnsZoneId
    dfsDnsZoneId: network.outputs.dfsDnsZoneId
    apiIdentityPrincipalId: identity.outputs.apiIdentityPrincipalId
    privateNetworking: privateNetworking
    enableDefenderScanning: enableDefenderScanning
    documentsImmutabilityDays: documentsImmutabilityDays
    lockImmutabilityPolicy: lockImmutabilityPolicy
    fabricWorkspaceIdentityPrincipalId: fabricWorkspaceIdentityPrincipalId
  }
}

module sql 'modules/sql.bicep' = {
  name: 'sql-${env}'
  params: {
    location: location
    env: env
    tags: tags
    peSubnetId: network.outputs.peSubnetId
    sqlDnsZoneId: network.outputs.sqlDnsZoneId
    workspaceId: monitoring.outputs.workspaceId
    privateNetworking: privateNetworking
    sqlAdminGroupObjectId: sqlAdminGroupObjectId
    sqlAdminGroupName: sqlAdminGroupName
    skuName: sqlSkuName
    skuTier: sqlSkuTier
    skuCapacity: sqlSkuCapacity
    zoneRedundant: zoneRedundant
    autoPauseDelayMinutes: sqlAutoPauseDelayMinutes
    minCapacity: sqlMinCapacity
    backupStorageRedundancy: sqlBackupStorageRedundancy
  }
}

module acr 'modules/acr.bicep' = {
  name: 'acr-${env}'
  params: {
    location: location
    env: env
    tags: tags
    orgPrefix: orgPrefix
    peSubnetId: network.outputs.peSubnetId
    acrDnsZoneId: network.outputs.acrDnsZoneId
    apiIdentityPrincipalId: identity.outputs.apiIdentityPrincipalId
    migrationIdentityPrincipalId: identity.outputs.migrationIdentityPrincipalId
    sku: acrSku
    privateEndpoint: acrPrivateEndpoint && privateNetworking
  }
}

module swa 'modules/staticwebapps.bicep' = {
  name: 'swa-${env}'
  params: {
    env: env
    tags: tags
    swaLocation: swaLocation
    sku: swaSku
  }
}

module containerapps 'modules/containerapps.bicep' = {
  name: 'containerapps-${env}'
  params: {
    location: location
    env: env
    tags: tags
    acaSubnetId: network.outputs.acaSubnetId
    vnetId: network.outputs.vnetId
    workspaceCustomerId: monitoring.outputs.workspaceCustomerId
    workspaceId: monitoring.outputs.workspaceId
    apiIdentityId: identity.outputs.apiIdentityId
    apiIdentityName: identity.outputs.apiIdentityName
    apiIdentityClientId: identity.outputs.apiIdentityClientId
    enableDefenderScanning: enableDefenderScanning
    trustedProxyHops: deployFrontDoor ? 2 : 1
    migrationIdentityId: identity.outputs.migrationIdentityId
    migrationIdentityClientId: identity.outputs.migrationIdentityClientId
    acrLoginServer: acr.outputs.loginServer
    apiImage: apiImage
    appInsightsSecretUri: keyvault.outputs.appInsightsSecretUri
    internalIngress: privateNetworking
    allowedIngressCidrs: allowedIngressCidrs
    zoneRedundant: zoneRedundant
    workloadProfileType: workloadProfileType
    minReplicas: minReplicas
    maxReplicas: maxReplicas
    environmentName: environmentName
    logLevel: logLevel
    appPublicUrl: appPublicUrl
    sqlServerFqdn: sql.outputs.serverFqdn
    databaseName: sql.outputs.databaseName
    authTenantId: authTenantId
    authAudience: authAudience
    authAllowedAzp: authAllowedAzp
    stagingBlobEndpoint: storage.outputs.stagingBlobEndpoint
    documentsBlobEndpoint: storage.outputs.documentsBlobEndpoint
    teamsAppId: teamsAppId
  }
}

module frontdoor 'modules/frontdoor.bicep' = {
  name: 'frontdoor-${env}'
  params: {
    env: env
    tags: tags
    location: location
    enabled: deployFrontDoor
    pwaHostname: swa.outputs.pwaDefaultHostname
    adminHostname: swa.outputs.adminDefaultHostname
    apiFqdn: containerapps.outputs.apiFqdn
    managedEnvironmentId: containerapps.outputs.environmentId
  }
}

module fabricgateway 'modules/fabricgateway.bicep' = {
  name: 'fabricgateway-${env}'
  params: {
    required: privateNetworking
    gatewaySubnetId: network.outputs.gatewaySubnetId
  }
}

output apiFqdn string = containerapps.outputs.apiFqdn
output frontDoorHostname string = frontdoor.outputs.endpointHostname
output pwaHostname string = swa.outputs.pwaDefaultHostname
output adminHostname string = swa.outputs.adminDefaultHostname
output acrLoginServer string = acr.outputs.loginServer
output sqlServerFqdn string = sql.outputs.serverFqdn
output apiIdentityName string = identity.outputs.apiIdentityName
output migrationIdentityName string = identity.outputs.migrationIdentityName
output migrateJobName string = containerapps.outputs.migrateJobName
output documentsAccountName string = storage.outputs.documentsAccountName
output stagingAccountName string = storage.outputs.stagingAccountName
output keyVaultName string = keyvault.outputs.vaultName
output fabricGatewayStep string = fabricgateway.outputs.manualStep
