// prod: full topology (AZURE_DESIGN.md section 2). Private networking, Front Door Premium + WAF,
// zone-redundant SQL, immutable documents (5 years, policy unlocked until Legal closes pendiente 7).
// Identity values are placeholders: replace with the production Entra registrations from the identity team.
using '../main.bicep'

param env = 'prod'
param privateNetworking = true
param deployFrontDoor = true
param deployGatewaySubnet = true

param authTenantId = '00000000-0000-0000-0000-000000000000'
param authAudience = '00000000-0000-0000-0000-000000000021'
param authAllowedAzp = '00000000-0000-0000-0000-000000000022,00000000-0000-0000-0000-000000000023'
param authAdminAzp = '00000000-0000-0000-0000-000000000023'
param sqlAdminGroupObjectId = '00000000-0000-0000-0000-000000000010'
param sqlAdminGroupName = 'PIPELINE-SQL-Admins'
param fabricWorkspaceIdentityPrincipalId = ''
param teamsAppId = ''

param apiImage = 'mcr.microsoft.com/k8se/quickstart:latest' // replaced by the CI digest on deploy
param workloadProfileType = 'D4'
param minReplicas = 2
param maxReplicas = 4
param zoneRedundant = true
param sqlSkuName = 'GP_Gen5'
param sqlSkuTier = 'GeneralPurpose'
param sqlSkuCapacity = 2
param sqlBackupStorageRedundancy = 'GeoZone'
param acrSku = 'Premium'
param acrPrivateEndpoint = true
param swaSku = 'Standard'
param logDailyCapGb = 5
param logRetentionDays = 90
param enableDefenderScanning = true
param documentsImmutabilityDays = 1826
param lockImmutabilityPolicy = false
param environmentName = 'production'
param logLevel = 'INFO'
param appPublicUrl = 'https://pipeline-prod.azurefd.net'
// Alert recipients (backlog OBS); empty until the support rota exists.
param alertEmails = []
