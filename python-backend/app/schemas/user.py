"""
用户相关数据校验模型（Pydantic）
"""

from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class BaseResponse(BaseModel, Generic[T]):
    """
    通用响应包装类
    """

    code: int = Field(default=0, description="响应码，0表示成功")
    data: Optional[T] = Field(default=None, description="响应数据")
    message: str = Field(default="ok", description="响应消息")


# ============ 请求模型 ============


class UserRegisterRequest(BaseModel):
    """
    用户注册请求
    """

    user_account: str = Field(..., min_length=4, description="用户账号", alias="userAccount")
    user_password: str = Field(..., min_length=8, description="用户密码", alias="userPassword")
    check_password: str = Field(..., min_length=8, description="确认密码", alias="checkPassword")

    class Config:
        populate_by_name = True


class UserLoginRequest(BaseModel):
    """
    用户登录请求
    """

    user_account: str = Field(..., min_length=4, description="用户账号", alias="userAccount")
    user_password: str = Field(..., min_length=8, description="用户密码", alias="userPassword")

    class Config:
        populate_by_name = True


class UserQueryRequest(BaseModel):
    """
    用户分页查询请求（管理员）
    """

    user_account: Optional[str] = Field(None, description="用户账号", alias="userAccount")
    user_name: Optional[str] = Field(None, description="用户昵称", alias="userName")
    current: int = Field(default=1, ge=1, description="当前页码")
    page_size: int = Field(default=10, ge=1, le=100, description="每页条数", alias="pageSize")

    class Config:
        populate_by_name = True


class DeleteRequest(BaseModel):
    """
    删除请求
    """

    id: int = Field(..., description="要删除的用户ID")


# ============ 响应模型（数据脱敏） ============


class LoginUserVO(BaseModel):
    """
    登录用户视图对象
    """

    id: int = Field(..., description="用户ID")
    user_account: str = Field(..., description="用户账号", alias="userAccount")
    user_name: Optional[str] = Field(None, description="用户昵称", alias="userName")
    user_avatar: Optional[str] = Field(None, description="用户头像", alias="userAvatar")
    user_profile: Optional[str] = Field(None, description="用户简介", alias="userProfile")
    user_role: str = Field(..., description="用户角色", alias="userRole")
    create_time: datetime = Field(..., description="创建时间", alias="createTime")

    class Config:
        populate_by_name = True
        from_attributes = True


class UserVO(BaseModel):
    """
    管理端用户视图对象
    """

    id: int = Field(..., description="用户ID")
    user_account: str = Field(..., description="用户账号", alias="userAccount")
    user_name: Optional[str] = Field(None, description="用户昵称", alias="userName")
    user_avatar: Optional[str] = Field(None, description="用户头像", alias="userAvatar")
    user_profile: Optional[str] = Field(None, description="用户简介", alias="userProfile")
    user_role: str = Field(..., description="用户角色", alias="userRole")
    create_time: datetime = Field(..., description="创建时间", alias="createTime")
    update_time: datetime = Field(..., description="更新时间", alias="updateTime")

    class Config:
        populate_by_name = True
        from_attributes = True
