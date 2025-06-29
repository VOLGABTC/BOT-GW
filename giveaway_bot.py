# --- VERSION FINALE ET CORRIGÉE - 29 Juin 2025 ---
import os
import json
import random
import datetime
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Configuration ---
# !!! METTEZ VOTRE PROPRE ID TELEGRAM ICI !!!
ADMIN_USER_IDS = [6938893387] 

# Le token est lu depuis les variables d'environnement du serveur (Railway)
TOKEN = os.environ.get('TOKEN')

# Dictionnaire pour stocker les giveaways actifs en mémoire
active_giveaways = {}

# --- Fonctions Utilitaires ---

def parse_duration(duration_str: str) -> datetime.timedelta | None:
    """Analyse une chaîne de durée (ex: '10h', '30m', '2d') et retourne un timedelta."""
    match = re.match(r"(\d+)([hmd])", duration_str.lower())
    if not match:
        return None
    
    value, unit = int(match.group(1)), match.group(2)
    
    if unit == 'm':
        return datetime.timedelta(minutes=value)
    elif unit == 'h':
        return datetime.timedelta(hours=value)
    elif unit == 'd':
        return datetime.timedelta(days=value)
    return None

def format_giveaway_message(chat_id: int) -> str:
    """Met en forme le message du giveaway pour l'affichage."""
    giveaway = active_giveaways.get(chat_id)
    if not giveaway:
        return "Aucun giveaway en cours."

    prize = giveaway['prize']
    end_time = giveaway['end_time']
    host = giveaway['host_mention']
    participants_count = len(giveaway['participants'])
    winners_count = giveaway['winners_count']
    
    now = datetime.datetime.now(end_time.tzinfo)
    time_left = end_time - now
    
    if time_left.total_seconds() <= 0:
        time_left_str = "terminé !"
    else:
        # Affichage simplifié du temps restant
        days = time_left.days
        hours, remainder = divmod(time_left.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        if days > 0:
            time_left_str = f"dans {days}j {hours}h"
        elif hours > 0:
            time_left_str = f"dans {hours}h {minutes}m"
        else:
            time_left_str = f"dans {minutes}m"

    end_time_str = end_time.strftime("%d %b %Y à %H:%M")

    return (
        f"🎉 **{prize}** 🎉\n\n"
        f"**Se termine :** {time_left_str} (le {end_time_str})\n"
        f"**Organisé par :** {host}\n"
        f"**Participants :** {participants_count}\n"
        f"**Gagnants :** {winners_count}"
    )

# --- Commandes du Bot ---

async def giveaway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lance un nouveau giveaway. Format: /giveaway <gagnants> <durée> <prix>"""
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("Désolé, seul un administrateur peut lancer un giveaway.")
        return

    chat_id = update.message.chat_id
    if chat_id in active_giveaways:
        await update.message.reply_text("Un giveaway est déjà en cours dans ce chat ! Attendez la fin du précédent.")
        return

    try:
        # CORRECTION DU BUG : On lit les arguments SANS le '_' au début
        winners_count_str, duration_str, *prize_list = context.args
        winners_count = int(winners_count_str)
        prize = ' '.join(prize_list)
        duration = parse_duration(duration_str)

        if not prize or not duration or winners_count <= 0:
            raise ValueError("Arguments invalides")
            
    except (ValueError, IndexError):
        await update.message.reply_text(
            "Format incorrect.\n"
            "Usage : `/giveaway <gagnants> <durée> <prix>`\n"
            "Exemple : `/giveaway 2 1h Super Lot`\n"
            "(Durées : `m` pour minutes, `h` pour heures, `d` pour jours)"
        )
        return

    end_time = datetime.datetime.now(datetime.timezone.utc) + duration
    host_user = update.effective_user
    
    giveaway_data = {
        "prize": prize,
        "end_time": end_time,
        "host_mention": host_user.mention_markdown_v2(),
        "winners_count": winners_count,
        "participants": {},  # {user_id: user_full_name}
        "message_id": None,
        "chat_id": chat_id
    }
    active_giveaways[chat_id] = giveaway_data

    message_text = format_giveaway_message(chat_id)
    keyboard = [[InlineKeyboardButton("🎉 Participer", callback_data='participate_giveaway')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    sent_message = await update.message.reply_markdown_v2(message_text, reply_markup=reply_markup)
    
    giveaway_data['message_id'] = sent_message.message_id

    context.job_queue.run_once(draw_winners_callback, when=end_time, data={"chat_id": chat_id}, name=f"gw_{chat_id}")
    await update.message.reply_text(f"Giveaway pour '{prize}' lancé ! Le tirage aura lieu dans {duration_str}.")

async def participate_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère le clic sur le bouton de participation."""
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    if chat_id not in active_giveaways:
        await query.answer("Désolé, ce giveaway est déjà terminé.", show_alert=True)
        return

    giveaway = active_giveaways[chat_id]
    if user.id in giveaway['participants']:
        await query.answer("Vous participez déjà !", show_alert=True)
    else:
        giveaway['participants'][user.id] = user.full_name
        await query.answer("Participation enregistrée. Bonne chance !", show_alert=True)
        
        new_text = format_giveaway_message(chat_id)
        keyboard = [[InlineKeyboardButton("🎉 Participer", callback_data='participate_giveaway')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(text=new_text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN_V2)
        except Exception as e:
            print(f"Ne peut pas éditer le message (pas de changement) : {e}")

async def draw_winners_callback(context: ContextTypes.DEFAULT_TYPE):
    """Fonction appelée par le job_queue pour effectuer le tirage."""
    chat_id = context.job.data['chat_id']
    
    if chat_id not in active_giveaways:
        return
        
    giveaway = active_giveaways[chat_id]
    participants = giveaway['participants']
    participants_ids = list(participants.keys())
    winners_count = min(giveaway['winners_count'], len(participants_ids)) # On ne peut pas tirer plus de gagnants que de participants
    prize = giveaway['prize']

    final_message = f"🎉 Le giveaway pour **{prize}** est terminé !\n\n"

    if not participants_ids:
        final_message += "Malheureusement, personne n'a participé 😕"
    else:
        winner_ids = random.sample(participants_ids, k=winners_count)
        # Pour mentionner les utilisateurs, il faut échapper les caractères spéciaux pour MarkdownV2
        winner_mentions = [f"🏆 [{participants[wid].replace('-', ' ')}](tg://user?id={wid})" for wid in winner_ids]
        
        final_message += "Félicitations aux gagnants :\n" + "\n".join(winner_mentions)
    
    await context.bot.send_message(chat_id, final_message, parse_mode=constants.ParseMode.MARKDOWN_V2)
    del active_giveaways[chat_id]

def main():
    """Lance le bot."""
    if not TOKEN:
        print("Erreur: Le token n'a pas été trouvé. Assurez-vous de l'avoir configuré dans les variables d'environnement.")
        return

    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("giveaway", giveaway_command))
    application.add_handler(CallbackQueryHandler(participate_button, pattern='^participate_giveaway$'))

    print("Le bot de giveaway (version finale) est démarré...")
    application.run_polling()

if __name__ == '__main__':
    main()