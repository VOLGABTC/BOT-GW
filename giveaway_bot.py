# --- VERSION FINALE V9 - COMMANDE REROLL ET HISTORIQUE ---
import os
import json
import random
import datetime
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import telegram.error

# --- Configuration ---
ADMIN_USER_IDS = [6938893387] # !!! METTEZ VOTRE PROPRE ID TELEGRAM ICI !!!
TOKEN = os.environ.get('TOKEN')
active_giveaways = {}

# --- Fichiers de stockage ---
ROLES_FILE = "roles.json"
HISTORY_FILE = "giveaway_history.json" # Nouveau fichier pour l'historique

# --- Fonctions Utilitaires et Gestion des Rôles (inchangées) ---
# ... (Toutes les fonctions de escape_markdown_v2 à save_roles restent identiques) ...
def escape_markdown_v2(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def parse_duration(duration_str: str) -> datetime.timedelta | None:
    match = re.match(r"(\d+)([hmd])", duration_str.lower())
    if not match: return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == 'm': return datetime.timedelta(minutes=value)
    elif unit == 'h': return datetime.timedelta(hours=value)
    elif unit == 'd': return datetime.timedelta(days=value)
    return None

def format_giveaway_message(giveaway_key: str) -> str:
    # ... (inchangée) ...
    giveaway = active_giveaways.get(giveaway_key)
    if not giveaway: return "Aucun giveaway en cours."
    prize, end_time, host = giveaway['prize'], giveaway['end_time'], giveaway['host_mention']
    participants_count, winners_count = len(giveaway['participants']), giveaway['winners_count']
    now = datetime.datetime.now(end_time.tzinfo)
    time_left = end_time - now
    if time_left.total_seconds() <= 0: time_left_str = "terminé !"
    else:
        days, remainder = divmod(int(time_left.total_seconds()), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        if days > 0: time_left_str = f"dans {days}j {hours}h"
        elif hours > 0: time_left_str = f"dans {hours}h {minutes}m"
        elif minutes > 0: time_left_str = f"dans {minutes}m {seconds}s"
        else: time_left_str = f"dans {seconds}s"
    end_time_str = end_time.strftime("%d %b %Y à %H:%M")
    message = ( f"🎉 *{prize}* 🎉\n\n" f"*Se termine :* {time_left_str} \\(le {end_time_str}\\)\n" f"*Organisé par :* {host}\n" f"*Participants :* {participants_count}\n" f"*Gagnants :* {winners_count}" )
    if giveaway.get("required_role"): message += f"\n*Réservé au rôle :* `{giveaway['required_role']}`"
    return message

def load_roles():
    # ... (inchangée) ...
    try:
        with open(ROLES_FILE, 'r') as f:
            content = f.read()
            if not content: return {}
            return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError): return {}

def save_roles(roles_data):
    # ... (inchangée) ...
    with open(ROLES_FILE, 'w') as f:
        json.dump(roles_data, f, indent=4)

# --- NOUVELLES FONCTIONS POUR L'HISTORIQUE ---
def load_history():
    """Charge l'historique des giveaways depuis le fichier JSON."""
    try:
        with open(HISTORY_FILE, 'r') as f:
            content = f.read()
            if not content: return {}
            return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError):
        return {} # Format: {"message_id_annonce_gagnants": {giveaway_data}}

def save_history(history_data):
    """Sauvegarde l'historique des giveaways dans le fichier JSON."""
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history_data, f, indent=4)

# --- Tâches planifiées (Jobs) ---
# ... (update_countdown_job et final_minute_trigger_job sont inchangées) ...
async def update_countdown_job(context: ContextTypes.DEFAULT_TYPE):
    # ... (inchangée) ...
    giveaway_key = context.job.data['giveaway_key']
    if giveaway_key not in active_giveaways:
        context.job.schedule_removal()
        return
    giveaway = active_giveaways[giveaway_key]
    new_text = format_giveaway_message(giveaway_key)
    keyboard = [[InlineKeyboardButton("🎉 Participer", callback_data=f'participate_{giveaway_key}')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await context.bot.edit_message_text(chat_id=giveaway['chat_id'], message_id=giveaway['message_id'], text=new_text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN_V2)
    except Exception as e:
        if "Message is not modified" not in str(e):
            print(f"Erreur compte à rebours: {e}")
            context.job.schedule_removal()

async def final_minute_trigger_job(context: ContextTypes.DEFAULT_TYPE):
    # ... (inchangée) ...
    giveaway_key = context.job.data['giveaway_key']
    print(f"Giveaway {giveaway_key}: Passage au décompte final.")
    slow_update_jobs = context.job_queue.get_jobs_by_name(f"gw_update_slow_{giveaway_key}")
    for job in slow_update_jobs: job.schedule_removal()
    context.job_queue.run_repeating(update_countdown_job, interval=3, data={"giveaway_key": giveaway_key}, name=f"gw_update_fast_{giveaway_key}")

# --- MODIFICATION DE LA FONCTION DE TIRAGE ---
async def draw_winners_callback(context: ContextTypes.DEFAULT_TYPE):
    """Effectue le tirage, puis sauvegarde le résultat dans l'historique."""
    giveaway_key = context.job.data['giveaway_key']
    for job_name in [f"gw_update_slow_{giveaway_key}", f"gw_update_fast_{giveaway_key}"]:
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
    if giveaway_key not in active_giveaways: return
    
    giveaway = active_giveaways[giveaway_key]
    chat_id, message_thread_id = giveaway['chat_id'], giveaway['message_thread_id']
    participants, prize = giveaway['participants'], giveaway['prize']
    
    # ... (la logique de sélection des gagnants est inchangée) ...
    final_message, winner_ids = f"🎉 Le giveaway pour *{prize}* est terminé \\! 🎉\n\n", []
    required_role, valid_participants = giveaway.get("required_role"), {}
    if required_role:
        roles = load_roles()
        if required_role in roles:
            for uid, uname in participants.items():
                if int(uid) in roles[required_role] or int(uid) in ADMIN_USER_IDS: valid_participants[uid] = uname
    else: valid_participants = participants
    valid_participant_ids = list(valid_participants.keys())
    winners_count = min(giveaway['winners_count'], len(valid_participant_ids))
    if not valid_participant_ids:
        final_message += "Malheureusement, aucun participant valide n'a été trouvé pour ce giveaway\\. 😕"
    else:
        winner_ids_str = random.sample(valid_participant_ids, k=winners_count)
        winner_ids = [int(wid) for wid in winner_ids_str] # On s'assure que les IDs sont des entiers
        mentions = [f"🏆 [{escape_markdown_v2(valid_participants[wid_str])}](tg://user?id={wid_str})" for wid_str in winner_ids_str]
        final_message += "Félicitations aux gagnants :\n" + "\n".join(mentions)

    # Envoi du message des gagnants
    winner_announcement_message = await context.bot.send_message(
        chat_id, final_message, parse_mode=constants.ParseMode.MARKDOWN_V2, message_thread_id=message_thread_id
    )

    # --- NOUVELLE LOGIQUE DE SAUVEGARDE ---
    # Au lieu de supprimer, on sauvegarde dans l'historique
    history = load_history()
    history_entry = {
        "prize": giveaway['prize'],
        "participants": giveaway['participants'], # Dictionnaire {user_id_str: user_name}
        "winner_ids": winner_ids # Liste [user_id_int]
    }
    # La clé de l'historique est l'ID du message d'annonce des gagnants
    history[str(winner_announcement_message.message_id)] = history_entry
    save_history(history)

    # On supprime enfin le giveaway de la liste des giveaways *actifs*
    if giveaway_key in active_giveaways:
        del active_giveaways[giveaway_key]

# --- Commandes du Bot ---

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (inchangée, mais on pourrait ajouter /reroll) ...
    help_text = "..." # Le message d'aide
    await update.message.reply_text(text=help_text, parse_mode=constants.ParseMode.MARKDOWN_V2)

# ... (assign_role, remove_role, cancel_giveaway, giveaway, participate_button sont inchangées) ...

# --- NOUVELLE COMMANDE /reroll ---
async def reroll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tire un nouveau gagnant pour un giveaway terminé."""
    if update.effective_user.id not in ADMIN_USER_IDS:
        return await update.message.reply_text("Désolé, seul un administrateur peut faire un reroll.")
    if not update.message.reply_to_message:
        return await update.message.reply_text("Usage : Répondez au message d'annonce des gagnants avec `/reroll`.")
        
    reroll_message_id = str(update.message.reply_to_message.message_id)
    history = load_history()

    if reroll_message_id not in history:
        return await update.message.reply_text("Je ne trouve pas ce giveaway dans mon historique. Assurez-vous de répondre au bon message.")

    giveaway_data = history[reroll_message_id]
    all_participants = giveaway_data['participants']
    previous_winners = giveaway_data['winner_ids']

    # On crée la liste des participants éligibles (ceux qui n'ont pas encore gagné)
    # On compare les IDs en tant qu'entiers pour être sûr
    eligible_participants = {uid: uname for uid, uname in all_participants.items() if int(uid) not in previous_winners}
    
    if not eligible_participants:
        return await update.message.reply_text("Il n'y a plus aucun participant éligible à tirer au sort pour ce giveaway.")

    # On tire un nouveau gagnant
    new_winner_id_str = random.choice(list(eligible_participants.keys()))
    new_winner_id = int(new_winner_id_str)
    new_winner_name = eligible_participants[new_winner_id_str]
    
    # On l'ajoute à la liste des gagnants dans l'historique
    giveaway_data['winner_ids'].append(new_winner_id)
    save_history(history)
    
    # On annonce le nouveau gagnant
    winner_mention = f"[{escape_markdown_v2(new_winner_name)}](tg://user?id={new_winner_id})"
    reroll_message = f"📢 **Reroll !** 📢\n\nUn nouveau gagnant a été tiré pour le concours *{giveaway_data['prize']}*.\n\nFélicitations à notre nouvel élu : {winner_mention} 🎉"

    await update.message.reply_text(reroll_message, parse_mode=constants.ParseMode.MARKDOWN_V2)


def main():
    """Lance le bot."""
    if not TOKEN:
        print("Erreur: Le token n'a pas été trouvé.")
        return

    application = ApplicationBuilder().token(TOKEN).build()

    # On ajoute la nouvelle commande /reroll
    application.add_handler(CommandHandler("reroll", reroll_command))
    
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("start", help_command))
    application.add_handler(CommandHandler("giveaway", giveaway_command))
    application.add_handler(CommandHandler("annuler_giveaway", cancel_giveaway_command))
    application.add_handler(CommandHandler("assigner_role", assign_role_command))
    application.add_handler(CommandHandler("retirer_role", remove_role_command))
    application.add_handler(CallbackQueryHandler(participate_button, pattern=r'^participate_'))
    
    print("Le bot de giveaway (version V9 - Reroll) est démarré...")
    application.run_polling()

if __name__ == '__main__':
    main()