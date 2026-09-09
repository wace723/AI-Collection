import { Navigate, Outlet } from 'react-router-dom'
import { getToken } from '../utils/auth'

/** 路由守卫：无 token 跳登录页 */
export default function RequireAuth() {
  if (!getToken()) {
    return <Navigate to="/login" replace />
  }
  return <Outlet />
}
