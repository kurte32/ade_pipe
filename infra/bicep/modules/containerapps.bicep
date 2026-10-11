// Container Apps environment, API app and background jobs (ADR-001).
// Configuration flows: Bicep params -> container env vars -> backend/app/core/config.py Settings.

param location string
param env string
param tags object
param acaSubnetId string
param vnetId string
param workspaceCustomerId string
param workspaceId string
param apiIdentityId string
param apiIdentityName string
param apiIdentityClientId string
@description('When false, SCAN_MODE falls back to none so uploads are not left waiting for scan tags that are never written (audit D-08).')
param enableDefenderScanning bool = true
@description('Reverse proxies that append to X-Forwarded-For before the API: 1 = Container Apps ingress, 2 = Front Door + ingress. Needs confirmation in the test environment (Phase 3).')
@minValue(0)
@maxValue(3)
param trustedProxyHops int = 2
@description('Revision that keeps 100% of traffic during this deployment. Empty on the first deployment (the new revision takes all traffic). The deploy workflow passes the revision serving now, runs the migration job, then shifts traffic explicitly (ADR-010, audit D-03).')
param trafficRevision string = ''
param migrationIdentityId string
param migrationIdentityClientId string
param acrLoginServer string
@description('Fully qualified image reference, by digest in CI: <acr>/pipeline-api@sha256:...')
param apiImage string
param appInsightsSecretUri string
@description('Internal ingress (Front Door Private Link origin) when true; public ingress with IP restrictions when false (dev).')
param internalIngress bool = true
@description('CIDR list allowed to reach the public ingress when internalIngress is false.')
param allowedIngressCidrs array = []
param zoneRedundant bool = true
@description('Dedicated workload profile for the API. Empty string uses Consumption.')
param workloadProfileType string = 'D4'
param minReplicas int = 1
param maxReplicas int = 3
param cpu string = '1.0'
param memory string = '2Gi'

// Application settings (production guard in config.py requires the entra/azure/defender/graph modes).
param environmentName string = 'production'
param logLevel string = 'INFO'
param appPublicUrl string
param sqlServerFqdn string
param databaseName string
param authTenantId string
param authAudience string
param authAllowedAzp string
@description('Client id of the admin SPA registration: Admin is honoured only from it.')
param authAdminAzp string
@description('Comma-separated SPA origins allowed by CORS. Empty behind Front Door (same origin); the SWA hosts when there is no Front Door (dev, audit INF-2).')
param corsAllowedOrigins string = ''
param stagingBlobEndpoint string
param documentsBlobEndpoint string
param stagingContainer string = 'staging'
param documentsContainer string = 'documents'
param teamsAppId string = ''
param graphBaseUrl string = 'https://graph.microsoft.com/v1.0'
param retentionYears int = 5

var envName = 'cae-pipeline-${env}'
var appName = 'ca-pipeline-api-${env}'
var useDedicated = !empty(workloadProfileType)
var profileName = useDedicated ? 'api' : 'Consumption'
var loginEndpoint = environment().authentication.loginEndpoint
var authIssuer = '${loginEndpoint}${authTenantId}/v2.0'
var authJwksUrl = '${loginEndpoint}${authTenantId}/discovery/v2.0/keys'

var commonEnv = [
  { name: 'ENVIRONMENT', value: environmentName }
  { name: 'LOG_LEVEL', value: logLevel }
  { name: 'APP_PUBLIC_URL', value: appPublicUrl }
  { name: 'DB_HOST', value: sqlServerFqdn }
  { name: 'DB_PORT', value: '1433' }
  { name: 'DB_NAME', value: databaseName }
  { name: 'DB_AUTH', value: 'entra' }
  { name: 'DB_USER', value: apiIdentityName }
  { name: 'AUTH_MODE', value: 'entra' }
  { name: 'AUTH_TENANT_ID', value: authTenantId }
  { name: 'AUTH_AUDIENCE', value: authAudience }
  { name: 'AUTH_ALLOWED_AZP', value: authAllowedAzp }
  { name: 'AUTH_ADMIN_AZP', value: authAdminAzp }
  { name: 'CORS_ALLOWED_ORIGINS', value: corsAllowedOrigins }
  { name: 'AUTH_ISSUER', value: authIssuer }
  { name: 'AUTH_JWKS_URL', value: authJwksUrl }
  { name: 'STORAGE_MODE', value: 'azure' }
  { name: 'STORAGE_STAGING_ACCOUNT_URL', value: stagingBlobEndpoint }
  { name: 'STORAGE_DOCUMENTS_ACCOUNT_URL', value: documentsBlobEndpoint }
  { name: 'STORAGE_STAGING_CONTAINER', value: stagingContainer }
  { name: 'STORAGE_DOCUMENTS_CONTAINER', value: documentsContainer }
  { name: 'SCAN_MODE', value: enableDefenderScanning ? 'defender' : 'none' }
  { name: 'TRUSTED_PROXY_HOPS', value: string(trustedProxyHops) }
  { name: 'NOTIFY_MODE', value: 'graph' }
  { name: 'DIRECTORY_MODE', value: 'graph' }
  { name: 'GRAPH_BASE_URL', value: graphBaseUrl }
  { name: 'TEAMS_APP_ID', value: teamsAppId }
  { name: 'RETENTION_YEARS', value: string(retentionYears) }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection-string' }
]

// DefaultAzureCredential selects the user-assigned identity through AZURE_CLIENT_ID.
var apiEnv = concat(commonEnv, [{ name: 'AZURE_CLIENT_ID', value: apiIdentityClientId }])
var migrationEnv = concat(commonEnv, [{ name: 'AZURE_CLIENT_ID', value: migrationIdentityClientId }])

resource managedEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  tags: tags
  properties: {
    zoneRedundant: zoneRedundant
    vnetConfiguration: {
      infrastructureSubnetId: acaSubnetId
      internal: internalIngress
    }
    workloadProfiles: concat(
      [
        { name: 'Consumption', workloadProfileType: 'Consumption' }
      ],
      useDedicated
        ? [
            {
              name: 'api'
              workloadProfileType: workloadProfileType
              minimumCount: 1
              maximumCount: 3
            }
          ]
        : []
    )
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspaceCustomerId
        sharedKey: listKeys(workspaceId, '2022-10-01').primarySharedKey
      }
    }
  }
}

// Internal environments need a private DNS zone for their default domain so VNet clients and
// Front Door Private Link resolve the app FQDN. The zone name is a runtime value, hence a module.
module envDns 'acadns.bicep' = if (internalIngress) {
  name: 'acadns-${env}'
  params: {
    defaultDomain: managedEnv.properties.defaultDomain
    staticIp: managedEnv.properties.staticIp
    vnetId: vnetId
    tags: tags
  }
}

var ipRestrictions = [
  for (cidr, i) in allowedIngressCidrs: {
    name: 'allow-${i}'
    action: 'Allow'
    ipAddressRange: cidr
  }
]

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${apiIdentityId}': {} }
  }
  properties: {
    managedEnvironmentId: managedEnv.id
    workloadProfileName: profileName
    configuration: {
      activeRevisionsMode: 'Multiple'
      maxInactiveRevisions: 5
      ingress: {
        external: true
        targetPort: 8000
        traffic: empty(trafficRevision)
          ? [{ latestRevision: true, weight: 100 }]
          : [{ revisionName: trafficRevision, weight: 100 }]
        transport: 'auto'
        allowInsecure: false
        ipSecurityRestrictions: internalIngress ? [] : ipRestrictions
      }
      registries: [
        { server: acrLoginServer, identity: apiIdentityId }
      ]
      secrets: [
        {
          name: 'appinsights-connection-string'
          keyVaultUrl: appInsightsSecretUri
          identity: apiIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          resources: { cpu: json(cpu), memory: memory }
          env: apiEnv
          probes: [
            {
              type: 'Startup'
              httpGet: { path: '/healthz', port: 8000 }
              initialDelaySeconds: 5
              periodSeconds: 5
              failureThreshold: 12
            }
            {
              type: 'Liveness'
              httpGet: { path: '/healthz', port: 8000 }
              periodSeconds: 15
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/readyz', port: 8000 }
              periodSeconds: 15
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http'
            http: { metadata: { concurrentRequests: '50' } }
          }
        ]
      }
    }
  }
}

var jobs = [
  { name: 'migrate', trigger: 'Manual', cron: '', command: ['sh', '-c', 'python -m app.cli db-init && alembic upgrade head'], identityId: migrationIdentityId, env: migrationEnv, timeout: 1800 }
  { name: 'promote', trigger: 'Schedule', cron: '*/1 * * * *', command: ['python', '-m', 'app.jobs.run', 'promote'], identityId: apiIdentityId, env: apiEnv, timeout: 600 }
  { name: 'outbox', trigger: 'Schedule', cron: '*/1 * * * *', command: ['python', '-m', 'app.jobs.run', 'outbox'], identityId: apiIdentityId, env: apiEnv, timeout: 300 }
  { name: 'expire-uploads', trigger: 'Schedule', cron: '*/10 * * * *', command: ['python', '-m', 'app.jobs.run', 'expire_uploads'], identityId: apiIdentityId, env: apiEnv, timeout: 600 }
  { name: 'purge', trigger: 'Schedule', cron: '0 3 * * *', command: ['python', '-m', 'app.jobs.run', 'purge'], identityId: apiIdentityId, env: apiEnv, timeout: 3600 }
  { name: 'idempotency-cleanup', trigger: 'Schedule', cron: '0 4 * * *', command: ['python', '-m', 'app.jobs.run', 'idempotency_cleanup'], identityId: apiIdentityId, env: apiEnv, timeout: 600 }
]

resource jobResources 'Microsoft.App/jobs@2024-03-01' = [
  for job in jobs: {
    name: 'caj-pipeline-${job.name}-${env}'
    location: location
    tags: tags
    identity: {
      type: 'UserAssigned'
      userAssignedIdentities: { '${job.identityId}': {} }
    }
    properties: {
      environmentId: managedEnv.id
      workloadProfileName: 'Consumption'
      configuration: {
        triggerType: job.trigger
        replicaTimeout: job.timeout
        replicaRetryLimit: 1
        manualTriggerConfig: job.trigger == 'Manual' ? { parallelism: 1, replicaCompletionCount: 1 } : null
        scheduleTriggerConfig: job.trigger == 'Schedule'
          ? { cronExpression: job.cron, parallelism: 1, replicaCompletionCount: 1 }
          : null
        registries: [
          { server: acrLoginServer, identity: job.identityId }
        ]
        secrets: [
          {
            name: 'appinsights-connection-string'
            keyVaultUrl: appInsightsSecretUri
            identity: job.identityId
          }
        ]
      }
      template: {
        containers: [
          {
            name: job.name
            image: apiImage
            command: job.command
            resources: { cpu: json('0.5'), memory: '1Gi' }
            env: job.env
          }
        ]
      }
    }
  }
]

output environmentId string = managedEnv.id
output environmentDefaultDomain string = managedEnv.properties.defaultDomain
output apiFqdn string = api.properties.configuration.ingress.fqdn
output apiName string = api.name
output apiLatestRevision string = api.properties.latestRevisionName
output migrateJobName string = 'caj-pipeline-migrate-${env}'
