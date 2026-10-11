// Log Analytics workspace + workspace-based Application Insights (ADR-010, PRODUCTION_READINESS.md section 2).

param location string
param env string
param tags object
@description('Daily ingestion cap in GB. -1 disables the cap.')
param dailyCapGb int = 1
param retentionDays int = 90
@description('Alert recipients. Empty: no action group or alert rules are deployed.')
param alertEmails array = []

resource workspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'log-pipeline-${env}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: retentionDays
    workspaceCapping: { dailyQuotaGb: dailyCapGb }
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
    features: { disableLocalAuth: false }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-pipeline-${env}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    Flow_Type: 'Bluefield'
    Request_Source: 'rest'
    WorkspaceResourceId: workspace.id
    IngestionMode: 'LogAnalytics'
    RetentionInDays: retentionDays
    DisableLocalAuth: false
  }
}

// Alert set from PRODUCTION_READINESS.md section 7 / OPERATIONS.md, as scheduled query rules on
// the API's JSON logs (backlog OBS). Thresholds are first guesses to tune in the test environment.
resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = if (!empty(alertEmails)) {
  name: 'ag-pipeline-${env}'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'pipeline'
    enabled: true
    emailReceivers: [
      for (email, i) in alertEmails: { name: 'email${i}', emailAddress: email, useCommonAlertSchema: true }
    ]
  }
}

var apiLogs = 'ContainerAppConsoleLogs_CL | where ContainerAppName_s startswith "ca-pipeline-api-" or ContainerAppName_s startswith "caj-pipeline-" | extend j = parse_json(Log_s)'
var alertRules = [
  {
    name: 'api-5xx-rate'
    description: 'API 5xx above 5 % of requests over 10 minutes (RB-10)'
    severity: 2
    query: '${apiLogs} | where j.event == "request" | summarize total = count(), errors = countif(toint(j.status) >= 500) | where total >= 20 and errors * 100.0 / total > 5'
    windowMinutes: 10
    frequencyMinutes: 5
  }
  {
    name: 'jobs-failed'
    description: 'A background job failed or the purge hit an error (RB-03, RB-07)'
    severity: 2
    query: '${apiLogs} | where j.event in ("job_failed", "purge_failed") | summarize count()'
    windowMinutes: 60
    frequencyMinutes: 15
  }
  {
    name: 'notifications-dead-lettered'
    description: 'A Teams notification exhausted its retries (RB-03)'
    severity: 3
    query: '${apiLogs} | where j.event == "outbox_run" and toint(j.fallidas) > 0 | summarize count()'
    windowMinutes: 60
    frequencyMinutes: 15
  }
  {
    name: 'purge-blocked'
    description: 'The retention purge was blocked by a legal hold or immutability policy (RB-07, Legal)'
    severity: 2
    query: '${apiLogs} | where j.event == "purge_blocked" | summarize count()'
    windowMinutes: 1440
    frequencyMinutes: 60
  }
]

resource alerts 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = [
  for rule in alertRules: if (!empty(alertEmails)) {
    name: 'alert-pipeline-${env}-${rule.name}'
    location: location
    tags: tags
    properties: {
      description: rule.description
      severity: rule.severity
      enabled: true
      scopes: [workspace.id]
      evaluationFrequency: 'PT${rule.frequencyMinutes}M'
      windowSize: 'PT${rule.windowMinutes}M'
      criteria: {
        allOf: [
          {
            query: rule.query
            timeAggregation: 'Count'
            operator: 'GreaterThan'
            threshold: 0
            failingPeriods: { numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1 }
          }
        ]
      }
      actions: { actionGroups: [actionGroup!.id] }
      autoMitigate: true
    }
  }
]

output workspaceId string = workspace.id
output workspaceCustomerId string = workspace.properties.customerId
output appInsightsId string = appInsights.id
output appInsightsConnectionString string = appInsights.properties.ConnectionString
