"""
运行时上下文注入中间件
从runtime提取user_id等信息，在agent启动时注入到systemmessage，agent无需调用工具，即可获取使用者身份，进而读取偏好文件。
"""
