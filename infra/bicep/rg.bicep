// Subscription-scoped: resource group per environment with tags and, for test/prod, a delete lock.

targetScope = 'subscription'

@allowed(['dev', 'test', 'prod'])
param env string
param location string
param owner string = 'Subdireccion de Inteligencia Artificial'

var tags = {
  environment: env
  workload: 'pipeline-tiendas'
  owner: owner
}

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-pipeline-${env}'
  location: location
  tags: tags
}

module lock 'modules/rglock.bicep' = if (env != 'dev') {
  name: 'lock-${env}'
  scope: rg
  params: {
    env: env
  }
}

output resourceGroupName string = rg.name
