<template>
  <div id="userRegisterPage">
    <h2 class="title">AI 大模型评测平台 - 用户注册</h2>
    <div class="desc">不写一行代码，生成完整模型评测报告</div>
    <a-form :model="formState" autocomplete="off" @finish="handleSubmit">
      <a-form-item
        name="userAccount"
        :rules="[
          { required: true, message: '请输入账号' },
          { min: 4, message: '账号长度不能小于 4 位' },
        ]"
      >
        <a-input v-model:value="formState.userAccount" placeholder="请输入账号（至少 4 位）" />
      </a-form-item>
      <a-form-item
        name="userPassword"
        :rules="[
          { required: true, message: '请输入密码' },
          { min: 8, message: '密码长度不能小于 8 位' },
        ]"
      >
        <a-input-password v-model:value="formState.userPassword" placeholder="请输入密码" />
      </a-form-item>
      <a-form-item
        name="checkPassword"
        :rules="[
          { required: true, message: '请确认密码' },
          { validator: validateCheckPassword },
        ]"
      >
        <a-input-password v-model:value="formState.checkPassword" placeholder="请确认密码" />
      </a-form-item>
      <div class="tips">
        已有账号？
        <RouterLink to="/user/login">去登录</RouterLink>
      </div>
      <a-form-item>
        <a-button type="primary" html-type="submit" style="width: 100%">注册</a-button>
      </a-form-item>
    </a-form>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { userRegister } from '@/api/user.ts'

const formState = reactive<{
  userAccount: string
  userPassword: string
  checkPassword: string
}>({
  userAccount: '',
  userPassword: '',
  checkPassword: '',
})

const router = useRouter()

// 校验确认密码是否一致
const validateCheckPassword = async (_rule: unknown, value: string) => {
  if (value && value !== formState.userPassword) {
    return Promise.reject('两次输入密码不一致')
  }
  return Promise.resolve()
}

const handleSubmit = async (values: any) => {
  // 校验两次输入的密码是否一致
  if (formState.userPassword !== formState.checkPassword) {
    message.error('两次输入密码不一致')
    return
  }
  try {
    const res = await userRegister(values)
    if (res.data.code === 0 && res.data.data) {
      message.success('注册成功')
      router.push({
        path: '/user/login',
        replace: true,
      })
    } else {
      message.error('注册失败，' + res.data.message)
    }
  } catch (e: any) {
    // 422 等错误已在全局拦截器中提示，这里兜底
    if (!e?.response) {
      message.error('注册失败，请稍后重试')
    }
  }
}
</script>

<style scoped>
#userRegisterPage {
  max-width: 360px;
  margin: 0 auto;
  padding-top: 80px;
}

.title {
  text-align: center;
  margin-bottom: 16px;
}

.desc {
  text-align: center;
  color: #bbb;
  margin-bottom: 16px;
}

.tips {
  margin-bottom: 16px;
  color: #bbb;
  font-size: 13px;
  text-align: right;
}
</style>
