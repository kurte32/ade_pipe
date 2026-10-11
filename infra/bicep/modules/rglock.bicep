// CanNotDelete lock on the resource group (test and prod). Break-glass: remove the lock with
// `az lock delete`, which is audited in the Activity Log (PRODUCTION_READINESS.md deployment gates).

param env string

resource lock 'Microsoft.Authorization/locks@2020-05-01' = {
  name: 'lock-pipeline-${env}-nodelete'
  properties: {
    level: 'CanNotDelete'
    notes: 'Protects production-grade resources, immutable storage and backups. Remove only via the documented break-glass procedure.'
  }
}
