// dev: consumption profile, serverless SQL, no Front Door, public ingress with IP restriction,
// no VNet data gateway (Mirroring off), Defender scanning on. See AZURE_DESIGN.md section 5.
// Identity values are placeholders: replace with the dev Entra registrations from the identity team.
using '../main.bicep'

param env = 'dev'
param privateNetworking = false
param deployFrontDoor = false
param deployGatewaySubnet = false
param allowedIngressCidrs = ['0.0.0.0/0'] // replace with the office/VPN CIDR before deploying

param authTenantId = '00000000-0000-0000-0000-000000000000'
param authAudience = '00000000-0000-0000-0000-000000000001'
param authAllowedAzp = '00000000-0000-0000-0000-000000000002,00000000-0000-0000-0000-000000000003'
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
