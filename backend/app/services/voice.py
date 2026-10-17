import asyncio
from pathlib import Path
import tempfile
import os
from typing import Optional, Dict, List
from datetime import datetime
import time

try:
    import whisper
except ImportError:
    whisper = None

try:
    import torch
except ImportError:
    torch = None

try:
    import dashscope
    from dashscope.audio.tts import SpeechSynthesizer
except ImportError:
    dashscope = None
    SpeechSynthesizer = None

try:
    from opencc import OpenCC
except ImportError:
    OpenCC = None

# 强制使用CPU
if torch is not None:
    torch.cuda.is_available = lambda: False


class VoiceService:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            print("创建VoiceService实例...")
            cls._instance = super(VoiceService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # 确保初始化代码只运行一次
        if not VoiceService._initialized:
            print("初始化VoiceService...")
            # 初始化Whisper模型
            print("正在加载Whisper模型...")
            # 获取当前文件的目录
            current_dir = Path(__file__).parent.parent.parent.parent  # 回到项目根目录
            model_path = current_dir / "backend" / "models" / "base.pt"

            if not os.path.exists(model_path):
                print(f"模型文件不存在于路径：{model_path}")
                print("尝试使用默认模型 'base'...")
                model_path = "base"  # 如果本地文件不存在，使用默认模型

            self.model = None
            if whisper is None:
                print("Whisper not installed; voice recognition is disabled.")
            else:
                try:
                    self.model = whisper.load_model(model_path)
                    print(f"Whisper模型已成功加载：{model_path}")
                except Exception as e:
                    print(f"加载Whisper模型失败：{str(e)}")
                    print(f"请确保模型文件已下载到：{model_path}")
                    self.model = None

            # 设置DashScope API密钥
            api_key = os.getenv('DASHSCOPE_API_KEY', '')
            if not api_key:
                print("警告：未配置DASHSCOPE_API_KEY，语音合成功能将不可用。")
            if dashscope is not None:
                dashscope.api_key = api_key

            # 创建临时文件目录（使用本地路径）
            root_dir = Path(__file__).resolve().parents[3]
            self.temp_dir = root_dir / "backend" / "data" / "temp"
            self.temp_dir.mkdir(parents=True, exist_ok=True)

            VoiceService._initialized = True

    async def speech_to_text(self, audio_file_path: str, language: str = "zh") -> Dict:
        """
        使用Whisper将语音转换为文字
        """
        try:
            if self.model is None:
                raise Exception("语音识别不可用：Whisper 未安装或模型未加载")
            print(f"开始处理音频文件: {audio_file_path}")
            # 检查文件是否存在
            if not os.path.exists(audio_file_path):
                raise Exception(f"音频文件不存在: {audio_file_path}")

            # 检查文件大小
            file_size = os.path.getsize(audio_file_path)
            if file_size == 0:
                raise Exception("音频文件为空")
            print(f"音频文件大小: {file_size} bytes")

            # 使用Whisper进行语音识别
            result = self.model.transcribe(
                audio_file_path,
                language=language,
                task="transcribe"
            )

            # 确保结果不为空
            if not result or "text" not in result:
                raise Exception("语音识别结果为空")

            result_text = result['text']
            if OpenCC is not None:
                cc = OpenCC('t2s')
                result_text = cc.convert(result_text)

            print(f"识别结果: {result_text}")

            return {
                "success": True,
                "text": result_text.strip(),
                "language": result.get("language", language),
                "segments": result.get("segments", [])
            }
        except Exception as e:
            print(f"语音识别错误: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def text_to_speech(self, text: str, rate: Optional[str] = None, volume: Optional[str] = None) -> str:
        """
        使用阿里云DashScope将文字转换为语音
        """
        try:
            if SpeechSynthesizer is None:
                raise Exception("语音合成不可用：DashScope 未安装")
            # 确保临时目录存在
            os.makedirs(self.temp_dir, exist_ok=True)

            # 生成临时文件路径
            timestamp = int(time.time() * 1000)
            output_path = self.temp_dir / f"speech_{timestamp}.wav"

            # 调用DashScope进行语音合成
            print(f"正在生成语音: {text}")
            result = SpeechSynthesizer.call(
                model='sambert-zhichu-v1',
                text=text,
                sample_rate=48000,
                format='wav'
            )

            # 检查结果
            if result.get_audio_data() is None:
                raise Exception("语音合成失败：未获取到音频数据")

            # 保存音频文件
            with open(output_path, 'wb') as f:
                f.write(result.get_audio_data())

            # 检查文件是否生成成功
            if not os.path.exists(output_path):
                raise Exception("语音文件生成失败")

            print(f"语音文件已生成: {output_path}")
            return str(output_path)

        except Exception as e:
            print(f"语音合成错误: {str(e)}")
            raise Exception(f"语音合成失败: {str(e)}")

    async def save_audio_file(self, audio_file) -> str:
        """
        保存上传的音频文件
        """
        try:
            # 确保临时目录存在
            os.makedirs(self.temp_dir, exist_ok=True)

            # 生成临时文件路径
            timestamp = int(time.time() * 1000)
            temp_path = self.temp_dir / f"audio_{timestamp}.wav"

            # 保存文件
            content = await audio_file.read()
            if not content:
                raise Exception("上传的音频文件为空")

            with open(temp_path, "wb") as f:
                f.write(content)

            print(f"音频文件已保存: {temp_path}")
            return str(temp_path)
        except Exception as e:
            print(f"保存音频文件失败: {str(e)}")
            raise Exception(f"音频文件保存失败: {str(e)}")

    def cleanup_temp_files(self, max_age: int = 3600):
        """
        清理临时音频文件
        max_age: 文件最大保存时间（秒）
        """
        try:
            current_time = datetime.now().timestamp()
            for file in self.temp_dir.glob("*"):
                # 如果文件超过最大保存时间，删除它
                if current_time - file.stat().st_mtime > max_age:
                    try:
                        os.remove(file)
                    except Exception:
                        pass
        except Exception:
            pass


# 创建语音服务实例
voice_service = VoiceService()
