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
    {
      path: '/prompt-lab',
      name: 'PromptLabPage',
      component: () => import('@/pages/PromptLabPage.vue'),
      // 与模型对比页同构：自带左侧会话栏，隐藏全局顶部导航
      meta: { title: '提示词实验', fullscreen: true },
    },
    {
      path: '/code-mode',
      name: 'CodeModePage',
      component: () => import('@/pages/CodeModePage.vue'),
      // 代码模式：左侧会话栏 + 中间对话 + 右侧实时预览，同样占满整个视口
      meta: { title: '代码模式', fullscreen: true },
    },
    {
      path: '/scene-manage',
      name: 'SceneManagePage',
      component: () => import('@/pages/SceneManagePage.vue'),
      meta: { title: '场景管理' },
    },
    {
      path: '/batch-test',
      name: 'BatchTestPage',
      component: () => import('@/pages/BatchTestPage.vue'),
      meta: { title: '批量测试' },
    },
    {
      path: '/model-manage',
      name: 'ModelManagePage',
      component: () => import('@/pages/ModelManagePage.vue'),
      meta: { title: '模型管理' },
    },
    {
      path: '/statistics',
      name: 'StatisticsPage',
      component: () => import('@/pages/StatisticsPage.vue'),
      meta: { title: '数据统计' },
    },
    {
      path: '/test/report',
      name: 'TestReportPage',
      component: () => import('@/pages/TestReportPage.vue'),
      // 报告页通过 query 里的 taskId 拉取数据（/test/report?taskId=xxx）
      meta: { title: '测试报告' },
    },
  ],
})

export default router
