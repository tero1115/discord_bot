import os
import re
import discord

from discord import Member, app_commands
from discord.ext import commands
from dotenv import load_dotenv
from threading import Lock

from openai import OpenAI

load_dotenv()

### 전역 변수 ###

# 토큰 설정
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OPENAI_KEY = os.getenv('OPENAI_KEY')

# OpenAI API client 설정
openai_client = OpenAI(api_key=OPENAI_KEY)  # OpenAI 클라이언트는 별도의 변수로 설정

# Discord bot 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents = intents)

# 대화 기록 제한 수 (5세트로 설정, 필요 시 조정 가능)
MAX_HISTORY_LENGTH = 5

# 전역 대화 내역 저장소
conversation_history: list[dict[str, str]] = list[dict[str, str]]()

# GPT role 배열
system_roles_array: list[str] = list[str]()

# 동시 호출 방지를 위한 lock
chat_lock: Lock = Lock()

### 내부 함수 ###
def is_positive_number(number_str: str) -> bool:
    return bool(re.fullmatch(r'[1-9]\d*', number_str.strip()))
    
async def send_message(interaction: discord.Interaction, message: str):
    permission = interaction.channel.permissions_for(interaction.channel.guild.me)
    if permission.send_messages:
        if interaction.response.is_done():
            await interaction.followup.send(message) # interaction.response.defer 상태이며, 추가 메시지를 전달하는 과정 (defer 유지 시간은 최대 15분)
        else:
            await interaction.response.send_message(message) # 최초 메시지 반환 상태이며, 이후 메시지를 추가로 보낼 경우 followup.send()로 대체됨

### 이벤트 ###
@bot.event
async def on_ready():
    '''
    봇이 준비되었을 때 발생하는 이벤트
    '''
    
    # 로그인 상태 표시
    print(f'We have logged in as {bot.user.name}')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name="테스트"))
    
    # 명령어를 서버에 동기화
    try:    
        await bot.tree.sync()
        print('명령어 동기화 완료')
        
    except Exception as ex:
        print(f'명령어 동기화 실패: {ex}')
        
    
@bot.command(name = 'sync')
async def on_request_command_sync(context: commands.Context):
    await bot.tree.sync(guild = context.guild)
    await context.send('동기화 완료')
    
@bot.tree.command(name = 'hello', description = '봇이 인사합니다.')
async def on_request_hello(interaction: discord.Interaction):
    '''
    !gpt hello 명령이 전달되었을 때 발생하는 이벤트
    '''
    await send_message(interaction, '반갑습니다.')
    
@bot.tree.command(name = 'gpt', description = 'GPT 명령을 보냅니다.')
@app_commands.describe(function = 'GPT 기능 [([빈칸]), (역할추가), (역할제거), (역할확인)]')
@app_commands.describe(content = 'GPT에 보낼 내용')
async def on_request_gpt(interaction: discord.Interaction, function: str = '대화', content: str = None):
    # !gpt (function (optional)) (content (optional))
    
    # 작업 지연 처리
    await interaction.response.defer()
    
    # 작업 시작
    if not function in ['대화', '역할추가', '역할제거', '역할확인']: 
        await send_message(interaction, '올바르지 않은 GPT 명령어입니다.')
            
    else:
        if function == '대화':
            if not function and not content:
                await send_message(interaction, '질문을 입력해주세요')
                return
            
            await send_message(interaction, 'GPT-4에 질문 중...')
            
            try:
                # 동시 전송 방지
                chat_lock.acquire()
                
                # Chat GPT에 메시지 전송 후 대화 기록
                response = send_to_chatGpt(system_roles_array, content)
                conversation_history.append({"role": "user", "content": content})
                conversation_history.append({"role": "assistant", "content": response})
                
                # 대화 내역이 MAX_HISTORY_LENGTH를 넘으면 오래된 항목 제거, system 메시지는 제외
                # (Icrus): 'system' 메시지는 히스토리에 저장이 안되는 것 같은데? 일단 주석 처리할께.
                # user_assistant_messages = [msg for msg in conversation_history if msg["role"] != "system"]
                
                # 대화 내역 중 사용자와 GPT의 메시지만 유지하며 오래된 항목 제거
                while len(conversation_history) > MAX_HISTORY_LENGTH * 2:
                    del conversation_history[:2]

                # 응답 전송
                await send_message(interaction, f"GPT-4 응답: {response}")
                
            except Exception as ex:
                await send_message(interaction, f'GPT 4 오류 발생: {ex}')
            
            finally:
                # 동시 전송 방지 해제
                chat_lock.release()
            
        elif function == '역할추가':
            # content가 비어있는 경우 처리
            if not content:
                await send_message(interaction, '추가할 역할을 입력해주세요.')
                return
            
            # 역할 추가 및 응답 전송
            system_roles_array.append(content)
            await send_message(interaction, f"역할 '{content}'이(가) 추가되었습니다.")
            
        elif function == '역할제거':
            # content가 비어있는 경우 처리
            if not content:
                await send_message(interaction, '제거할 역할의 숫자를 선택해주세요.')
                return
            
            # content가 양수가 아닌 경우 처리
            elif not is_positive_number(content):
                await send_message(interaction, '올바른 숫자를 입력해주세요 ("역할확인" 에서 출력되는 번호를 참조해주세요).')
                return
            
            # content를 정수 타입으로 변환 후, 유효성 확인 후 응답 전송
            role_index = int(content)
            if 1 <= role_index < len(system_roles_array) + 1:  # 번호가 유효한지 확인
                removed_role = system_roles_array.pop(role_index - 1)
                await send_message(interaction, f"역할 '{removed_role}'이(가) 제거되었습니다.")
            
            else:
                await send_message(interaction, '해당 번호로 등록된 역할이 존재하지 않습니다.')
                
        elif function == '역할확인':
            if system_roles_array:
                response = '현재 역할 목록:\n'
                for i in range(len(system_roles_array)):
                    response += f'{i + 1}. {system_roles_array[i]}\n'

                await send_message(interaction, response)
                
            else:
                await send_message(interaction, '저장된 역할이 없습니다.')

        if not content:
            await send_message(interaction, '질문을 입력해주세요.')
            return

def send_to_chatGpt(system_roles_array,question, model = "gpt-4o-2024-08-06"):
    try:
        # 새로운 질문이 있을 때마다 현재 활성화된 역할을 추가
        messages = [{"role": "system", "content": role} for role in system_roles_array if role]

        # 대화 내역 중에서 content가 있는 항목만 추가
        messages.extend([msg for msg in conversation_history if msg["content"]])

        # 질문이 있는지 확인 후 추가
        if question:

            # 기존 유저와 GPT 간의 대화 내역 추가
            messages.extend(conversation_history)

            # 사용자 질문 추가
            messages.append({"role": "user", "content": question,})

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

# 봇 시작
bot.run(DISCORD_TOKEN)
