# Нейро-блогер Instagram

Telegram-бот: Grok пишет сценарий на **o'zbek** (vaqt sayohati: o'tmish va kelajak) и делает Reel **30с** 480p, сам кладёт в **@motivstile.ai**.

Пульт: `@Traning_with_Albert_bot`.

**24/7:** https://neuro-blogger.onrender.com (Render free + webhook). Локальный `ctl.sh start` не гонять — конфликт с webhook.

Avtopilot: 30s o'zbek reels (3×10s). Каждая следующая сцена стартует с последнего кадра + портрет персонажа, чтобы **голова/лицо не менялись**. 8/день в **часы пик Ташкента**. Ночью не посит.

UptimeRobot: HTTP каждые 5 мин на `https://neuro-blogger.onrender.com/health`.

Grok: сессия grok.com или `XAI_API_KEY`. Автопост включён.
