/** 登录占位：infra-002 实现，infra-001 不调用 */
export async function login(_username: string, _password: string): Promise<void> {
  throw new Error('登录接口在 infra-002 实现')
}
