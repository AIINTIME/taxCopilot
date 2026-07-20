export const routePermissions: Record<string, string> = {
  '/': 'dashboard.view',
  '/new-chat': 'chat.create',
  '/deep-research': 'deep_research.use',
  '/it-act-comparison': 'it_act.compare',
  '/analytics': 'analytics.view',
  '/security-audit': 'security_audit.view',
  '/projects/new': 'projects.manage',
  '/personal-tax': 'chat.create',
  '/corporate': 'chat.create',
  '/capital-gains': 'chat.create',
  '/notices': 'chat.create',
}

export function hasPermission(permissions: string[] | undefined, permission: string) {
  return Boolean(permissions?.includes(permission))
}
