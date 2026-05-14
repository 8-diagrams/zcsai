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

def list_available_models():
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
        models_response = client.models.list()
        models = models_response.data

        # 4. 打印结果
        print(f"\n✅ 查询成功！当前节点共有 【{len(models)}】 个可用模型：")
        print("-" * 50)
        
        sorted_models = sorted(models, key=lambda m: m.id)
        
        for i, model in enumerate(sorted_models, 1):
            owner = getattr(model, 'owned_by', 'unknown')
            print(f"{i:03d} | 🤖 {model.id} (Owner: {owner})")
            
        print("-" * 50)
        print("💡 提示: 挑选您喜欢的模型名称，填入 .env 文件的 LLM_MODEL_NAME 中即可。")

    except Exception as e:
        print(f"\n❌ 查询失败！请检查 .env 中的 Key 和 URL 是否正确，或者网络是否连通。")
        print(f"📄 详细报错: {e}")

if __name__ == "__main__":
    list_available_models()