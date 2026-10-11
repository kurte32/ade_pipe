// test: same topology as production with smaller SKUs (AZURE_DESIGN.md section 5). UAT environment.
// Identity values are placeholders: replace with the test Entra registrations from the identity team.
using '../main.bicep'

param env = 'test'
param privateNetworking = true
param deployFrontDoor = true
param deployGatewaySubnet = true

param authTenantId = '00000000-0000-0000-0000-000000000000'
param authAudience = '00000000-0000-0000-0000-000000000011'
param authAllowedAzp = '00000000-0000-0000-0000-000000000012,00000000-0000-0000-0000-000000000013'
param authAdminAzp = '00000000-0000-0000-0000-000000000013'
param sqlAdminGroupObjectId = '00000000-0000-0000-0000-000000000010'
param sqlAdminGroupName = 'PIPELINE-SQL-Admins-test'
param fabricWorkspaceIdentityPrincipalId = ''
param teamsAppId = ''

param apiImage = 'mcr.microsoft.com/k8se/quickstart:latest' // replaced by the CI digest on deploy
param workloadProfileType = 'D4'
param minReplicas = 1
param maxReplicas = 2
param zoneRedundant = true
param sqlSkuName = 'GP_Gen5'
param sqlSkuTier = 'GeneralPurpose'
param sqlSkuCapacity = 2
param sqlBackupStorageRedundancy = 'Zone'
param acrSku = 'Premium'
param acrPrivateEndpoint = true
param swaSku = 'Standard'
param logDailyCapGb = 2
param logRetentionDays = 30
param enableDefenderScanning = true
param documentsImmutabilityDays = 1
param lockImmutabilityPolicy = false
param environmentName = 'test'
param logLevel = 'INFO'
param appPublicUrl = 'https://pipeline-test.azurefd.net'
