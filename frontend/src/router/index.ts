import { createRouter, createWebHistory } from 'vue-router'
import HomePage from '@/pages/HomePage.vue'
import UserLoginPage from '@/pages/user/UserLoginPage.vue'
import UserRegisterPage from '@/pages/user/UserRegisterPage.vue'
import UserManagePage from '@/pages/admin/UserManagePage.vue'
import ChatPage from '@/pages/ChatPage.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: '主页',
      component: HomePage,
    },
    {
      path: '/user/login',
      name: '用户登录',
      component: UserLoginPage,
    },
    {
      path: '/user/register',
      name: '用户注册',
      component: UserRegisterPage,
    },
    {
      path: '/admin/userManage',
      name: '用户管理',
      component: UserManagePage,
    },
    {
      path: '/chat',
      name: 'AI 对话',
      component: ChatPage,
    },
    {
      path: '/side-by-side',
      name: 'SideBySidePage',
      component: () => import('@/pages/SideBySidePage.vue'),
      // fullscreen：该页自带左侧会话栏，隐藏全局顶部导航，占满整个视口
      meta: { title: '模型对比', fullscreen: true },
    },
  ],
})

export default router
