import os
import json
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai

app = Flask(__name__)

# LINEの設定
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Geminiの設定
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# 初期点数（4人分・名前をローマ字表記に変更）
current_scores = {
    "Ryosui": 25000,
    "Sho": 25000,
    "Yuya": 25000,
    "Kohei": 25000
}

SYSTEM_PROMPT = """
あなたは麻雀の点数移動を管理する優秀なエージェントです。
ユーザーから「現在の4人の点数」と「対局結果のテキスト」が送られてきます。
以下のルールに従って新しい点数（引き算・足し算）を計算し、必ず指定のJSONフォーマットでのみ出力してください。

【点数計算の基本ルール】
1. テキストに「3900」「8000」などの具体的な数字がある場合は、その点数を移動させます。
2. 「満貫」「跳満」「倍満」「三倍満」「役満」というキーワードがある場合は、以下の点数を適用します。
   - 満貫: 子 8000点 / 親 12000点
   - 跳満: 子 12000点 / 親 18000点
   - 倍満: 子 16000点 / 親 24000点
   - 三倍満: 子 24000点 / 親 36000点
   - 役満: 子 32000点 / 親 48000点

【アガリ情報の解釈ルール】
- ロン: アガった人にプラス、振り込んだ人にマイナス。
- ツモ: アガった人にプラス。支払いは、アガった人が「親」なら子が均等に支払い、「子」なら親が半分、残りの子が半分ずつ支払います。

【流局（リュウキョク）ルールの解釈】
テキストに「流局」や「ノーテン」といったキーワードがある場合は、テンパイ（聴牌）している人とノーテン（不聴）の人に分かれて、場風のノーテン罰符（計3000点）をやり取りします。
- 全員ノーテン、または全員テンパイ: 点数移動は「全員 0点」です。
- 1人テンパイ: テンパイした人が「+3000点」、ノーテンの3人が「-1000点」ずつ。
- 2人テンパイ: テンパイした2人が「+1500点」ずつ、ノーテンの2人が「-1500点」ずつ。
- 3人テンパイ: テンパイした3人が「+1000点」ずつ、ノーテンの1人が「-3000点」。
※もしテキストから誰がテンパイしているか判断できない場合は、successをfalseにして「誰がテンパイしてた？」と聞き返してください。

【名前の表記について】
ユーザーが日本語で「りょうすい」や「諒粋」と入力した場合でも、内部データの「Ryosui」として正しく処理してください。

【出力フォーマット】
一切の解説文を排除し、必ず以下のJSON形式でのみ返答してください。Markdownの枠組み（```json 等）も含めず、純粋なJSON文字列のみを出力してください。
{
  "success": true,
  "message": "LINEでユーザーに返す分かりやすい報告文（例：流局ですね。Shoさん1人テンパイなので+3000点、他3人は-1000点です）",
  "new_scores": {
    "Ryosui": 25000,
    "Sho": 25000,
    "Yuya": 25000,
    "Kohei": 25000
  }
}
"""

@app.route("/webhook", methods=['POST'])
def webhook():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global current_scores
    user_message = event.message.text

    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"{SYSTEM_PROMPT}\n\n現在の点数:\n{json.dumps(current_scores, ensure_ascii=False)}\n\n対局結果:\n「{user_message}」"
        
        response = model.generate_content(prompt)
        ai_reply = response.text.strip()
        
        result = json.loads(ai_reply)
        
        if result.get("success"):
            current_scores = result.get("new_scores")
            reply_text = f"{result.get('message')}\n\n【現在の持ち点】\n"
            for name, score in current_scores.items():
                reply_text += f"・{name}: {score}点\n"
        else:
            reply_text = result.get("message")
            
    except Exception as e:
        reply_text = f"エラーが発生しました。もう一度入力するか、言い方を変えてみてください。（詳細: {str(e)}）"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)