from openai import OpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict

# ==========================================
# 1. 复用 FastAPI 的配置读取逻辑
# ==========================================
class Settings(BaseSettings):
    LLM_API_KEY: str
    LLM_BASE_URL: str
    
    # 告诉 Pydantic 去哪里找配置文件 (忽略不需要的字段)
    model_config = SettingsConfigDict(env_file=".env.code", env_file_encoding="utf-8", extra="ignore")

def test_model( model ):
    print("=== 🚀 AI 大模型可用列表查询工具 (自动读取 .env) ===")
    
    try:
        # 实例化配置，它会自动去读 .env 文件
        settings = Settings()
        
        if not settings.LLM_API_KEY:
            print("❌ 错误：在 .env 中未找到 LLM_API_KEY！")
            return
            
        print(f"🌐 正在连接目标节点: {settings.LLM_BASE_URL}")
        
        # 2. 初始化 OpenAI 客户端
        client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL
        )

        # 3. 发送请求获取模型列表
        models_response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "user", "content": "你是什么模型?"}
                    ],
                    max_tokens=50,
                    temperature=0.1,
                    timeout=15.0
                )
        
        print("✅ 测试成功！模型回复内容：")
        print(f"\033[92m{response.choices[0].message.content}\033[0m")

    except Exception as e:
        print(f"\n❌ 查询失败！请检查 .env 中的 Key 和 URL 是否正确，或者网络是否连通。")
        print(f"📄 详细报错: {e}")

if __name__ == "__main__":
    #test_model("claude-opus-4-7")
    test_model("gpt-5.5")