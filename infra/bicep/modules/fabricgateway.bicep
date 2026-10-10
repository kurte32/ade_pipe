// Fabric VNet data gateway placeholder (ADR-008, AZURE_DESIGN.md section 3 zone 5).
// The gateway itself is created from the Fabric portal (Manage connections and gateways) and attached to
// the delegated subnet created in network.bicep. Bicep cannot create it. This module only exposes the
// subnet id as a documented output and records the parameter for the deployment summary.

@description('True when Mirroring must reach Azure SQL through its private endpoint (private networking).')
param required bool = true
param gatewaySubnetId string = ''

output gatewayRequired bool = required
output gatewaySubnetId string = gatewaySubnetId
output manualStep string = required
  ? 'Create a VNet data gateway in Fabric (Settings > Manage connections and gateways) on subnet ${gatewaySubnetId}, then configure Mirroring with that gateway.'
  : 'Mirroring connects directly; no VNet data gateway needed.'
