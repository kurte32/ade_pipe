// Network: VNet, subnets (Container Apps, private endpoints, Fabric VNet data gateway), NSGs,
// private DNS zones for SQL, Blob, Key Vault and ACR with VNet links. See AZURE_DESIGN.md section 3.

param location string
param env string
param tags object
param vnetAddressPrefix string = '10.40.0.0/16'
param acaSubnetPrefix string = '10.40.0.0/23'
param peSubnetPrefix string = '10.40.2.0/24'
param gatewaySubnetPrefix string = '10.40.3.0/27'
@description('Deploy the Fabric VNet data gateway subnet (ADR-008). The gateway itself is created in the Fabric portal.')
param deployGatewaySubnet bool = true

var vnetName = 'vnet-pipeline-${env}'

resource nsgAca 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: 'nsg-pipeline-aca-${env}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowVnetInbound'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          destinationPortRange: '*'
        }
      }
      {
        name: 'AllowAzureLoadBalancerInbound'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: '*'
          sourceAddressPrefix: 'AzureLoadBalancer'
          sourcePortRange: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          destinationPortRange: '*'
        }
      }
      {
        name: 'AllowFrontDoorBackendHttps'
        properties: {
          priority: 120
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'AzureFrontDoor.Backend'
          sourcePortRange: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowVnetOutbound'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          destinationPortRange: '*'
        }
      }
      {
        name: 'AllowEntraOutbound'
        properties: {
          priority: 110
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'AzureActiveDirectory'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowMonitorOutbound'
        properties: {
          priority: 120
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'AzureMonitor'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowMcrOutbound'
        properties: {
          priority: 130
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'MicrosoftContainerRegistry'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowAzureFrontDoorFirstPartyOutbound'
        properties: {
          priority: 140
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'AzureFrontDoor.FirstParty'
          destinationPortRange: '443'
        }
      }
      {
        // Azure SQL: 1433 plus the redirect port range (audit INF-2; a private endpoint is inside
        // the VNet and already allowed by AllowVnetOutbound).
        name: 'AllowSqlOutbound'
        properties: {
          priority: 150
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'Sql'
          destinationPortRanges: ['1433', '11000-11999']
        }
      }
      {
        // Microsoft Graph, Defender for Storage result endpoints and the Container Apps control plane
        // are not covered by a single service tag. Egress inspection is out of scope (ADR-008).
        name: 'AllowInternetHttpsOutbound'
        properties: {
          priority: 200
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'Internet'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowDnsOutbound'
        properties: {
          priority: 210
          direction: 'Outbound'
          access: 'Allow'
          protocol: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '53'
        }
      }
      {
        name: 'DenyAllOtherOutbound'
        properties: {
          priority: 4000
          direction: 'Outbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

resource nsgPe 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: 'nsg-pipeline-pe-${env}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowVnetInbound'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          destinationPortRange: '*'
        }
      }
      {
        name: 'DenyInternetInbound'
        properties: {
          priority: 4000
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

// Fabric VNet data gateway subnet (ADR-008, AZURE_DESIGN.md section 3 zone 5).
// Rules follow the documented gateway requirements: outbound 443 to Power BI / Fabric and SQL via private endpoint.
resource nsgGw 'Microsoft.Network/networkSecurityGroups@2023-11-01' = if (deployGatewaySubnet) {
  name: 'nsg-pipeline-gw-${env}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowVnetOutbound'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          destinationPortRange: '*'
        }
      }
      {
        name: 'AllowPowerBIOutbound'
        properties: {
          priority: 110
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'PowerBI'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowEntraOutbound'
        properties: {
          priority: 120
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'AzureActiveDirectory'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowInternetHttpsOutbound'
        properties: {
          priority: 200
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'Internet'
          destinationPortRange: '443'
        }
      }
    ]
  }
}

var gatewaySubnet = deployGatewaySubnet
  ? [
      {
        name: 'snet-gw'
        properties: {
          addressPrefix: gatewaySubnetPrefix
          networkSecurityGroup: { id: nsgGw.id }
          delegations: [
            {
              name: 'PowerPlatformVnetAccess'
              properties: { serviceName: 'Microsoft.PowerPlatform/vnetaccesslinks' }
            }
          ]
        }
      }
    ]
  : []

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: [vnetAddressPrefix] }
    subnets: concat(
      [
        {
          name: 'snet-aca'
          properties: {
            addressPrefix: acaSubnetPrefix
            networkSecurityGroup: { id: nsgAca.id }
            delegations: [
              {
                name: 'Microsoft.App.environments'
                properties: { serviceName: 'Microsoft.App/environments' }
              }
            ]
          }
        }
        {
          name: 'snet-pe'
          properties: {
            addressPrefix: peSubnetPrefix
            networkSecurityGroup: { id: nsgPe.id }
            privateEndpointNetworkPolicies: 'Enabled'
          }
        }
      ],
      gatewaySubnet
    )
  }
}

var zoneNames = [
  'privatelink${environment().suffixes.sqlServerHostname}'
  'privatelink.blob.${environment().suffixes.storage}'
  'privatelink.dfs.${environment().suffixes.storage}'
  'privatelink.vaultcore.azure.net'
  'privatelink.azurecr.io'
]

resource zones 'Microsoft.Network/privateDnsZones@2020-06-01' = [
  for zone in zoneNames: {
    name: zone
    location: 'global'
    tags: tags
  }
]

resource links 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [
  for (zone, i) in zoneNames: {
    parent: zones[i]
    name: '${vnetName}-link'
    location: 'global'
    tags: tags
    properties: {
      registrationEnabled: false
      virtualNetwork: { id: vnet.id }
    }
  }
]

output vnetId string = vnet.id
output acaSubnetId string = vnet.properties.subnets[0].id
output peSubnetId string = vnet.properties.subnets[1].id
output gatewaySubnetId string = deployGatewaySubnet ? vnet.properties.subnets[2].id : ''
output sqlDnsZoneId string = zones[0].id
output blobDnsZoneId string = zones[1].id
output dfsDnsZoneId string = zones[2].id
output vaultDnsZoneId string = zones[3].id
output acrDnsZoneId string = zones[4].id
