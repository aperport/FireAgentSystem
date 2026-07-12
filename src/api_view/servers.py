

import uuid

from fastapi import FastAPI, Response
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel
from util_tools.logger import get_logger
from agent.main_agent import start_main_agent

app = FastAPI()

logger = get_logger(__name__)
class query_user(BaseModel):
    user_name: str
    user_id: str
    query: str
    thread_id: str|None=None
class response(BaseModel):
    answer: str
    thread_id: str

@app.post("/talk",response_model=response)
async def talk(user: query_user,res: Response):
    if not user.thread_id:
        user.thread_id = uuid.uuid4().hex
    
    config: RunnableConfig = RunnableConfig(metadata={"user_id": f"{user.user_id}", "username": f"{user.user_name}"},run_name=f"{user.user_name}_main_agent"
                                             ,configurable={"thread_id": f"{user.thread_id}","user_id": f"{user.user_id}","username": f"{user.user_name}"})
    try:
        answer = await start_main_agent(user.query,config)
        return {"answer": answer,"thread_id": user.thread_id}
    except Exception as e:
        logger.error("询问失败，信息：%s", e)
        res.status_code = 500
        return {"answer": "询问失败，未找到相关回答","thread_id": user.thread_id}
