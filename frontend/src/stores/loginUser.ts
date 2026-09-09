import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getLoginUser, type LoginUserVO } from '@/api/user.ts'

/**
 * 登录用户类型：所有字段可选，未登录时仅有 userName 占位
 */
export type LoginUserType = Partial<LoginUserVO>

/**
 * 登录用户全局状态
 */
export const useLoginUserStore = defineStore('loginUser', () => {
  const loginUser = ref<LoginUserType>({
    userName: '未登录',
  })

  async function fetchLoginUser() {
    const res = await getLoginUser()
    if (res.data.code === 0 && res.data.data) {
      loginUser.value = res.data.data
    }
  }

  function setLoginUser(newLoginUser: LoginUserType) {
    loginUser.value = newLoginUser
  }

  return { loginUser, fetchLoginUser, setLoginUser }
})
