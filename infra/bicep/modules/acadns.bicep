// Private DNS zone for an internal Container Apps environment default domain. Separate module because
// the zone name is only known after the environment is created.

param defaultDomain string
param staticIp string
param vnetId string
param tags object

resource zone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: defaultDomain
  location: 'global'
  tags: tags
}

resource wildcard 'Microsoft.Network/privateDnsZones/A@2020-06-01' = {
  parent: zone
  name: '*'
  properties: {
    ttl: 300
    aRecords: [{ ipv4Address: staticIp }]
  }
}

resource link 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: zone
  name: 'aca-link'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnetId }
  }
}

output zoneId string = zone.id
