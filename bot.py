import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from openai import OpenAI

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OPENAI_KEY = os.getenv('OPENAI_KEY')

# Set up the OpenAI API client
openai_client = OpenAI(api_key=OPENAI_KEY)  # OpenAI 클라이언트는 별도의 변수로 설정

# Discord bot setup
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# 대화 기록 제한 수 (5개로 설정, 필요 시 조정 가능)
MAX_HISTORY_LENGTH = 5

# 전역 대화 내역 저장소
conversation_history = []

# GPT role 배열
system_roles_array = []

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user.name}')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name="테스트"))

@bot.event
async def on_message(message):
    global conversation_history  # 전역 변수를 사용하기 위해 global 선언

    if message.author == bot.user:
        return  # bot 스스로가 보낸 메시지는 무시

    # 'Hello'로 시작하는 메시지에 반응
    if message.content.startswith("Hello"):
        await message.channel.send("반갑습니다.")

    # !gpt-역할추가 명령어로 역할 추가
    if message.content.startswith("!gpt 역할추가"):
        role = message.content[len("!gpt 역할추가 "):].strip()  # 명령어 뒤의 역할을 추출
        if role:  # 빈 값이 아니면 배열에 추가
            system_roles_array.append(role)
            await message.channel.send(f"역할 '{role}'이(가) 추가되었습니다.")
        else:
            await message.channel.send("추가할 역할을 입력해주세요.")

    # !gpt-역할확인 명령어로 역할 목록 출력
    if message.content.startswith("!gpt 역할확인"):
        if system_roles_array:
            response = "현재 역할 목록:\n"
            for index, role in enumerate(system_roles_array, start=1):
                response += f"{index}. {role}\n"
            await message.channel.send(response)
        else:
            await message.channel.send("저장된 역할이 없습니다.")

    # !gpt-역할제거 [번호] 명령어로 번호에 해당하는 역할 제거
    if message.content.startswith("!gpt 역할제거"):
        try:
            # 번호 추출
            role_index = int(message.content[len("!gpt 역할제거 "):].strip()) - 1
            if 0 <= role_index < len(system_roles_array):  # 번호가 유효한지 확인
                removed_role = system_roles_array.pop(role_index)
                await message.channel.send(f"역할 '{removed_role}'이(가) 제거되었습니다.")
            else:
                await message.channel.send("유효한 번호를 입력해주세요.")
        except ValueError:
            await message.channel.send("올바른 번호를 입력해주세요.")

    # ChatGPT 관련 명령어 처리
    if message.content.startswith("!gpt 질문"):
        # GPT 명령 뒤의 내용을 가져옴
        question = message.content[8:]
        if question:
            await message.channel.send("GPT-4에 질문 중...")

            try:
                # ChatGPT에 메시지를 보냄
                response = send_to_chatGpt(system_roles_array, question)
                conversation_history.append({"role": "user", "content": question})  # 사용자 질문 저장
                conversation_history.append({"role": "assistant", "content": response})  # GPT 응답 저장

                # 대화 내역이 MAX_HISTORY_LENGTH를 넘으면 오래된 항목 제거, system 메시지는 제외
                user_assistant_messages = [msg for msg in conversation_history if msg["role"] != "system"]

                # 대화 내역 중 사용자와 GPT의 메시지만 유지하며 오래된 항목 제거
                if len(user_assistant_messages) > MAX_HISTORY_LENGTH * 2:
                    conversation_history = user_assistant_messages[-MAX_HISTORY_LENGTH*2:]

                await message.channel.send(f"GPT-4 응답: {response}")
            except Exception as e:
                await message.channel.send(f"오류 발생: {e}")
        else:
            await message.channel.send("질문을 입력해주세요.")

def send_to_chatGpt(system_roles_array,question, model = "gpt-4o-2024-08-06"):
    try:
        # 새로운 질문이 있을 때마다 현재 활성화된 역할을 추가
        messages = [{"role": "system", "content": role} for role in system_roles_array]

        # 기존 유저와 GPT 간의 대화 내역 추가
        messages.extend(conversation_history)

        # 사용자 질문 추가
        messages.append(
            {
                "role": "user",
                "content": question,
            }
        )

        # GPT에 질문을 전달하여 답변을 생성
        completion = openai_client.chat.completions.create(
            model=model,
            messages=messages,
        )
        print("completion : ", completion)
        print("messages : ", messages)
        # GPT 응답 반환
        return completion.choices[0].message.content

    except Exception as e:
        print(f"OpenAI API 호출 중 오류 발생: {e}")
        return "OpenAI API 호출 중 오류가 발생했습니다."

# Start the bot
bot.run(DISCORD_TOKEN)
