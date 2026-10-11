// User-assigned managed identities (AZURE_DESIGN.md section 4, ADR-008).
// apiIdentity: API container app and background jobs. migrationIdentity: Alembic job (SQL admin capable).

param location string
param env string
param tags object

resource apiIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-pipeline-api-${env}'
  location: location
  tags: tags
}

resource migrationIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-pipeline-migrate-${env}'
  location: location
  tags: tags
}

output apiIdentityId string = apiIdentity.id
output apiIdentityName string = apiIdentity.name
output apiIdentityPrincipalId string = apiIdentity.properties.principalId
output apiIdentityClientId string = apiIdentity.properties.clientId
output migrationIdentityId string = migrationIdentity.id
output migrationIdentityName string = migrationIdentity.name
output migrationIdentityPrincipalId string = migrationIdentity.properties.principalId
output migrationIdentityClientId string = migrationIdentity.properties.clientId
