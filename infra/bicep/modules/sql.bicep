// Azure SQL Database (ADR-002): Entra-only authentication, private endpoint, zone-redundant GP SKU,
// short- and long-term backup retention, auditing to Log Analytics.

param location string
param env string
param tags object
param peSubnetId string
param sqlDnsZoneId string
param workspaceId string
param privateNetworking bool = true
@description('Entra group that is the SQL server administrator. The migration identity must be a member.')
param sqlAdminGroupObjectId string
param sqlAdminGroupName string
param databaseName string = 'pipeline'
@description('Database SKU. Production: GP_Gen5 2 vCores zone-redundant. Dev: GP_S_Gen5 serverless.')
param skuName string = 'GP_Gen5'
param skuTier string = 'GeneralPurpose'
param skuCapacity int = 2
param zoneRedundant bool = true
@description('Serverless auto-pause delay in minutes (-1 disables). Only for GP_S_* SKUs.')
param autoPauseDelayMinutes int = -1
param minCapacity string = ''
param maxSizeBytes int = 34359738368
param shortTermRetentionDays int = 35
param ltrWeeklyRetention string = 'P12W'
param ltrMonthlyRetention string = 'P60M'
param ltrYearlyRetention string = 'P5Y'
param ltrWeekOfYear int = 1
@description('Backup storage redundancy: Zone, Geo or GeoZone.')
param backupStorageRedundancy string = 'GeoZone'

var serverName = 'sql-pipeline-${env}'

resource server 'Microsoft.Sql/servers@2023-05-01-preview' = {
  name: serverName
  location: location
  tags: tags
  properties: {
    version: '12.0'
    minimalTlsVersion: '1.2'
    publicNetworkAccess: privateNetworking ? 'Disabled' : 'Enabled'
    restrictOutboundNetworkAccess: 'Disabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      azureADOnlyAuthentication: true
      principalType: 'Group'
      login: sqlAdminGroupName
      sid: sqlAdminGroupObjectId
      tenantId: tenant().tenantId
    }
  }
}

// Without private networking (dev) the API and the migrate job reach the public endpoint from
// Container Apps egress addresses that are not fixed, so Azure services must be allowed (INF-2).
resource allowAzureServices 'Microsoft.Sql/servers/firewallRules@2023-05-01-preview' = if (!privateNetworking) {
  parent: server
  name: 'AllowAllWindowsAzureIps'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource entraOnly 'Microsoft.Sql/servers/azureADOnlyAuthentications@2023-05-01-preview' = {
  parent: server
  name: 'Default'
  properties: { azureADOnlyAuthentication: true }
}

resource database 'Microsoft.Sql/servers/databases@2023-05-01-preview' = {
  parent: server
  name: databaseName
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
    capacity: skuCapacity
  }
  properties: {
    collation: 'SQL_Latin1_General_CP1_CI_AS'
    maxSizeBytes: maxSizeBytes
    zoneRedundant: zoneRedundant
    requestedBackupStorageRedundancy: backupStorageRedundancy
    autoPauseDelay: autoPauseDelayMinutes
    minCapacity: empty(minCapacity) ? null : json(minCapacity)
    isLedgerOn: false
    readScale: 'Disabled'
  }
}

resource shortTerm 'Microsoft.Sql/servers/databases/backupShortTermRetentionPolicies@2023-05-01-preview' = {
  parent: database
  name: 'default'
  properties: {
    retentionDays: shortTermRetentionDays
    diffBackupIntervalInHours: 12
  }
}

resource longTerm 'Microsoft.Sql/servers/databases/backupLongTermRetentionPolicies@2023-05-01-preview' = {
  parent: database
  name: 'default'
  properties: {
    weeklyRetention: ltrWeeklyRetention
    monthlyRetention: ltrMonthlyRetention
    yearlyRetention: ltrYearlyRetention
    weekOfYear: ltrWeekOfYear
  }
}

resource auditing 'Microsoft.Sql/servers/auditingSettings@2023-05-01-preview' = {
  parent: server
  name: 'default'
  properties: {
    state: 'Enabled'
    isAzureMonitorTargetEnabled: true
    auditActionsAndGroups: [
      'SUCCESSFUL_DATABASE_AUTHENTICATION_GROUP'
      'FAILED_DATABASE_AUTHENTICATION_GROUP'
      'BATCH_COMPLETED_GROUP'
    ]
  }
}

resource master 'Microsoft.Sql/servers/databases@2023-05-01-preview' existing = {
  parent: server
  name: 'master'
}

resource masterDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'audit-to-log-analytics'
  scope: master
  properties: {
    workspaceId: workspaceId
    logs: [
      { category: 'SQLSecurityAuditEvents', enabled: true }
    ]
  }
  dependsOn: [auditing]
}

resource dbDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'db-to-log-analytics'
  scope: database
  properties: {
    workspaceId: workspaceId
    logs: [
      { category: 'SQLSecurityAuditEvents', enabled: true }
      { category: 'Errors', enabled: true }
      { category: 'Timeouts', enabled: true }
      { category: 'Deadlocks', enabled: true }
    ]
    metrics: [
      { category: 'Basic', enabled: true }
    ]
  }
}

resource pe 'Microsoft.Network/privateEndpoints@2023-11-01' = if (privateNetworking) {
  name: 'pe-${serverName}'
  location: location
  tags: tags
  properties: {
    subnet: { id: peSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'sqlServer'
        properties: {
          privateLinkServiceId: server.id
          groupIds: ['sqlServer']
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
        name: 'sql'
        properties: { privateDnsZoneId: sqlDnsZoneId }
      }
    ]
  }
}

output serverName string = server.name
output serverFqdn string = server.properties.fullyQualifiedDomainName
output databaseName string = database.name
output serverId string = server.id
