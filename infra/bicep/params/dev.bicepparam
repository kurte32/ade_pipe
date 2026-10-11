// dev: consumption profile, serverless SQL, no Front Door, public ingress with IP restriction,
// no VNet data gateway (Mirroring off), Defender scanning on. See AZURE_DESIGN.md section 5.
// Identity values are placeholders: replace with the dev Entra registrations from the identity team.
using '../main.bicep'

param env = 'dev'
param privateNetworking = false
param deployFrontDoor = false
param deployGatewaySubnet = false
// Fail-closed (audit D-07): the office/VPN CIDRs come from DEV_ALLOWED_INGRESS_CIDRS (comma-separated)
// at deploy time. Without it only 127.0.0.1/32 is allowed, i.e. nothing outside can reach the API.
// GitHub always defines the variable (empty when unset), so the default alone never applied; an
// empty value falls back to localhost only (fail closed, audit CI-3).
param allowedIngressCidrs = empty(trim(readEnvironmentVariable('DEV_ALLOWED_INGRESS_CIDRS', '')))
  ? ['127.0.0.1/32']
  : split(readEnvironmentVariable('DEV_ALLOWED_INGRESS_CIDRS', ''), ',')

param authTenantId = '00000000-0000-0000-0000-000000000000'
param authAudience = '00000000-0000-0000-0000-000000000001'
param authAllowedAzp = '00000000-0000-0000-0000-000000000002,00000000-0000-0000-0000-000000000003'
param authAdminAzp = '00000000-0000-0000-0000-000000000003'
param sqlAdminGroupObjectId = '00000000-0000-0000-0000-000000000010'
param sqlAdminGroupName = 'PIPELINE-SQL-Admins-dev'

param apiImage = 'mcr.microsoft.com/k8se/quickstart:latest' // replaced by the CI digest on deploy
param workloadProfileType = ''
param minReplicas = 0
param maxReplicas = 1
param zoneRedundant = false
param sqlSkuName = 'GP_S_Gen5'
param sqlSkuTier = 'GeneralPurpose'
param sqlSkuCapacity = 1
param sqlAutoPauseDelayMinutes = 60
param sqlMinCapacity = '0.5'
param sqlBackupStorageRedundancy = 'Local'
param acrSku = 'Standard'
param acrPrivateEndpoint = false
param swaSku = 'Free'
param logDailyCapGb = 1
param logRetentionDays = 30
param enableDefenderScanning = true
param documentsImmutabilityDays = 0
param lockImmutabilityPolicy = false
param environmentName = 'test'
param logLevel = 'DEBUG'
param appPublicUrl = 'https://swa-pipeline-pwa-dev.azurestaticapps.net'
// No Teams app yet (backlog TEAMS): the in-app feed only. Switch to graph once teamsAppId is set.
param notifyMode = 'log'
