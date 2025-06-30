# --- VERSION FINALE V11 - FINITION COMPTE A REBOURS ---
import os
import json
import random
import datetime
import re
import asyncio # NOUVEL IMPORT
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import telegram.error

# --- Configuration ---
# !!! METTEZ VOTRE PROPRE ID TELEGRAM ICI !!!
ADMIN_USER_IDS = [6938893387] 

TOKEN = os.environ.get('TOKEN')
active_giveaways = {}

# --- Fichiers de stockage ---
ROLES_FILE = "roles.json"
HISTORY_FILE = "giveaway_history.json"

# --- Fonctions Utilitaires ---
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

# --- Fonctions de Gestion des Rôles & Historique ---
def load_roles():
    try:
        with open(ROLES_FILE, 'r') as f:
            content = f.read()
            if not content: return {}
            return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError): return {}

def save_roles(roles_data):
    with open(ROLES_FILE, 'w') as f: json.dump(roles_data, f, indent=4)

def load_history():
    try:
        with open(HISTORY_FILE, 'r') as f:
            content = f.read()
            if not content: return {}
            return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError): return {}

def save_history(history_data):
    with open(HISTORY_FILE, 'w') as f: json.dump(history_data, f, indent=4)

# --- Tâches planifiées (Jobs) ---
async def update_countdown_job(context: ContextTypes.DEFAULT_TYPE):
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
    giveaway_key = context.job.data['giveaway_key']
    print(f"Giveaway {giveaway_key}: Passage au décompte final.")
    slow_update_jobs = context.job_queue.get_jobs_by_name(f"gw_update_slow_{giveaway_key}")
    for job in slow_update_jobs: job.schedule_removal()
    context.job_queue.run_repeating(update_countdown_job, interval=3, data={"giveaway_key": giveaway_key}, name=f"gw_update_fast_{giveaway_key}")

async def draw_winners_callback(context: ContextTypes.DEFAULT_TYPE):
    """Effectue le tirage, avec une mise à jour finale et une pause."""
    giveaway_key = context.job.data['giveaway_key']
    for job_name in [f"gw_update_slow_{giveaway_key}", f"gw_update_fast_{giveaway_key}"]:
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
    if giveaway_key not in active_giveaways: return
    
    giveaway = active_giveaways[giveaway_key]
    chat_id, message_thread_id = giveaway['chat_id'], giveaway['message_thread_id']

    # --- NOUVELLE PARTIE : MISE À JOUR FINALE DU MESSAGE ---
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=giveaway['message_id'],
            text=f"🎉 *{giveaway['prize']}* 🎉\n\n⌛️ *Tirage en cours\\.\\.\\.*",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=None # On retire le bouton "Participer"
        )
        await asyncio.sleep(2) # Petite pause pour le suspense
    except Exception as e:
        print(f"Erreur lors de la mise à jour finale du message : {e}")
    # --- FIN DE LA NOUVELLE PARTIE ---

    # Logique de tirage
    participants, prize = giveaway['participants'], giveaway['prize']
    final_message, winner_ids = f"🎉 Le giveaway pour *{prize}* est terminé \\! 🎉\n\n", []
    required_role, valid_participants = giveaway.get("required_role"), {}
    if required_role:
        roles = load_roles()
        if required_role in roles:
            for uid_str, uname in participants.items():
                uid = int(uid_str)
                if uid in roles[required_role] or uid in ADMIN_USER_IDS: valid_participants[uid_str] = uname
    else: valid_participants = participants
    valid_participant_ids = list(valid_participants.keys())
    winners_count = min(giveaway['winners_count'], len(valid_participant_ids))
    if not valid_participant_ids:
        final_message += "Malheureusement, aucun participant valide n'a été trouvé pour ce giveaway\\. 😕"
    else:
        winner_ids_str = random.sample(valid_participant_ids, k=winners_count)
        winner_ids = [int(wid) for wid in winner_ids_str]
        mentions = [f"🏆 [{escape_markdown_v2(valid_participants[wid_str])}](tg://user?id={wid_str})" for wid_str in winner_ids_str]
        final_message += "Félicitations aux gagnants :\n" + "\n".join(mentions)
    
    winner_announcement_message = await context.bot.send_message(chat_id, final_message, parse_mode=constants.ParseMode.MARKDOWN_V2, message_thread_id=message_thread_id)

    # Sauvegarde dans l'historique
    history = load_history()
    history_entry = { "prize": giveaway['prize'], "participants": giveaway['participants'], "winner_ids": winner_ids, "chat_id": chat_id, "message_thread_id": message_thread_id }
    history[str(winner_announcement_message.message_id)] = history_entry
    save_history(history)

    if giveaway_key in active_giveaways:
        del active_giveaways[giveaway_key]

# --- Commandes du Bot (inchangées) ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = "💡 *Voici la liste des commandes disponibles* 💡\n\n\\-\\-\\-\n\n*Commandes pour les Administrateurs*\n\n`/giveaway <gagnants> <durée> [@rôle] <prix>`\n_Lance un nouveau giveaway\\. Le rôle est optionnel\\._\n*Exemple:* `/giveaway 2 1h Super Lot`\n*Exemple avec rôle:* `/giveaway 1 30m @vip Lot VIP`\n\n`/annuler_giveaway`\n_Annule le concours en cours dans le chat et le sujet actuels\\._\n\n`/reroll`\n_\\(En réponse à un message de gagnants\\) Retire un nouveau gagnant\\._\n\n`/assigner_role <rôle>`\n_\\(En réponse à un message\\) Assigne un rôle à un utilisateur\\._\n\n`/retirer_role <rôle>`\n_\\(En réponse à un message\\) Retire un rôle à un utilisateur\\._\n\n`/help`\n_Affiche ce message d'aide\\._"
    await update.message.reply_text(text=help_text, parse_mode=constants.ParseMode.MARKDOWN_V2)

async def reroll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_USER_IDS: return await update.message.reply_text("Désolé, seul un administrateur peut faire un reroll.")
    if not update.message.reply_to_message: return await update.message.reply_text("Usage : Répondez au message d'annonce des gagnants avec `/reroll`.")
    reroll_message_id = str(update.message.reply_to_message.message_id)
    history = load_history()
    if reroll_message_id not in history: return await update.message.reply_text("Je ne trouve pas ce giveaway dans mon historique.")
    giveaway_data = history[reroll_message_id]
    all_participants, previous_winners = giveaway_data['participants'], giveaway_data['winner_ids']
    eligible_participants = {uid_str: uname for uid_str, uname in all_participants.items() if int(uid_str) not in previous_winners}
    if not eligible_participants: return await update.message.reply_text("Il n'y a plus aucun participant éligible à tirer au sort.")
    new_winner_id_str = random.choice(list(eligible_participants.keys()))
    new_winner_id, new_winner_name = int(new_winner_id_str), eligible_participants[new_winner_id_str]
    giveaway_data['winner_ids'].append(new_winner_id)
    save_history(history)
    winner_mention = f"[{escape_markdown_v2(new_winner_name)}](tg://user?id={new_winner_id})"
    reroll_message = f"📢 *Reroll \\!* 📢\n\nUn nouveau gagnant a été tiré pour le concours *{giveaway_data['prize']}*\\.\n\nFélicitations à notre nouvel élu : {winner_mention} 🎉"
    await update.message.reply_text(reroll_message, parse_mode=constants.ParseMode.MARKDOWN_V2)

async def assign_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_USER_IDS: return await update.message.reply_text("Désolé, seul un administrateur peut assigner un rôle.")
    if not update.message.reply_to_message: return await update.message.reply_text("Usage : Répondez au message d'un utilisateur avec `/assigner_role <nom_du_role>`")
    try: role_name, target_user_id, target_user_name = context.args[0].lower(), update.message.reply_to_message.from_user.id, update.message.reply_to_message.from_user.full_name
    except IndexError: return await update.message.reply_text("Format incorrect. N'oubliez pas le nom du rôle.")
    roles = load_roles()
    if role_name not in roles: roles[role_name] = []
    if target_user_id not in roles[role_name]:
        roles[role_name].append(target_user_id)
        save_roles(roles)
        await update.message.reply_text(f"Le rôle '{role_name}' a bien été assigné à {target_user_name}.")
    else: await update.message.reply_text(f"{target_user_name} a déjà le rôle '{role_name}'.")

async def remove_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_USER_IDS: return await update.message.reply_text("Désolé, seul un administrateur peut retirer un rôle.")
    if not update.message or not update.message.reply_to_message: return await update.message.reply_text("Usage : Répondez au message d'un utilisateur avec `/retirer_role <nom_du_role>`")
    try: role_name, target_user_id, target_user_name = context.args[0].lower(), update.message.reply_to_message.from_user.id, update.message.reply_to_message.from_user.full_name
    except IndexError: return await update.message.reply_text("Format incorrect. Usage: `/retirer_role <nom_du_role>`")
    roles = load_roles()
    if role_name in roles and target_user_id in roles[role_name]:
        roles[role_name].remove(target_user_id)
        if not roles[role_name]: del roles[role_name]
        save_roles(roles)
        await update.message.reply_text(f"Le rôle '{role_name}' a été retiré à {target_user_name}.")
    else: await update.message.reply_text(f"{target_user_name} n'a pas (ou plus) le rôle '{role_name}'.")

async def cancel_giveaway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, message_thread_id = update.message.chat_id, update.message.message_thread_id
    giveaway_key = f"{chat_id}_{message_thread_id}" if message_thread_id else str(chat_id)
    if update.effective_user.id not in ADMIN_USER_IDS: return await update.message.reply_text("Désolé, seul un administrateur peut annuler un giveaway.")
    if giveaway_key not in active_giveaways: return await update.message.reply_text("Il n'y a aucun giveaway en cours à annuler dans ce sujet.")
    for job_name in [f"gw_draw_{giveaway_key}", f"gw_update_slow_{giveaway_key}", f"gw_update_fast_{giveaway_key}", f"gw_final_minute_{giveaway_key}"]:
        for job in context.job_queue.get_jobs_by_name(job_name): job.schedule_removal()
    giveaway = active_giveaways[giveaway_key]
    prize = giveaway['prize']
    cancelled_text = f"❌ *GIVEAWAY ANNULÉ* ❌\n\nLe concours pour *{prize}* a été annulé par un administrateur\\."
    try:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=giveaway['message_id'], text=cancelled_text, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=None)
    except Exception as e: print(f"Erreur en éditant le message d'annulation: {e}")
    if giveaway_key in active_giveaways: del active_giveaways[giveaway_key]
    await update.message.reply_text("Le giveaway a bien été annulé.")

async def giveaway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lance un nouveau giveaway, avec la logique de parsing de rôle DÉFINITIVE ET ROBUSTE."""
    if update.effective_user.id not in ADMIN_USER_IDS:
        return await update.message.reply_text("Désolé, seul un administrateur peut lancer un giveaway.")
    
    chat_id, message_thread_id = update.message.chat_id, update.message.message_thread_id
    giveaway_key = f"{chat_id}_{message_thread_id}" if message_thread_id else str(chat_id)

    if giveaway_key in active_giveaways:
        return await update.message.reply_text("Un giveaway est déjà en cours dans ce sujet !")
        
    args = context.args
    if len(args) < 2: # On a besoin au minimum de <gagnants> <durée> <prix>
        return await update.message.reply_text(
            "Format incorrect.\nUsage : `/giveaway <gagnants> <durée> [@rôle] <prix>`\nExemple : `/giveaway 2 1h Super Lot`"
        )

    try:
        # --- LOGIQUE CORRIGÉE ET SIMPLIFIÉE ---
        winners_count = int(args[0])
        duration = parse_duration(args[1])
        
        required_role = None
        prize_start_index = 2  # Par défaut, le prix commence au 3ème argument

        # On vérifie si le 3ème argument ressemble à un rôle
        if len(args) > 2 and args[2].startswith('@'):
            potential_role = args[2][1:].lower()
            roles = load_roles()
            if potential_role in roles:
                required_role = potential_role
            # Si le rôle n'existe pas, on l'ignore mais on ne l'inclut pas dans le prix
            prize_start_index = 3 # Dans tous les cas, si ça commence par @, le prix commence après
        
        # On vérifie qu'il reste des mots pour le prix
        if len(args) <= prize_start_index:
            raise ValueError("Le nom du prix est manquant après le rôle.")

        prize = ' '.join(args[prize_start_index:])
        # --- FIN DE LA LOGIQUE CORRIGÉE ---

        if not prize or not duration or winners_count <= 0:
            raise ValueError("Arguments invalides")
            
    except (ValueError, IndexError) as e:
        # On peut afficher une erreur plus précise
        error_message = str(e) if str(e) else "Format invalide. Vérifiez les nombres et la durée (ex: 10m, 2h, 1d)."
        return await update.message.reply_text(error_message)

    # Le reste de la fonction est inchangé...
    end_time = datetime.datetime.now(datetime.timezone.utc) + duration
    host_user = update.effective_user
    escaped_prize = escape_markdown_v2(prize)

    giveaway_data = {
        "prize": escaped_prize,
        "required_role": required_role,
        "end_time": end_time,
        "host_mention": update.effective_user.mention_markdown_v2(),
        "winners_count": winners_count,
        "participants": {},
        "message_id": None,
        "chat_id": chat_id,
        "message_thread_id": message_thread_id
    }
    active_giveaways[giveaway_key] = giveaway_data
    
    message_text = format_giveaway_message(giveaway_key)
    keyboard = [[InlineKeyboardButton("🎉 Participer", callback_data=f'participate_{giveaway_key}')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        sent_message = await context.bot.send_message(
            chat_id,
            text=message_text,
            reply_markup=reply_markup,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            message_thread_id=message_thread_id
        )
        giveaway_data['message_id'] = sent_message.message_id
        
        image_url = "https://imgur.com/a/fGbNYQ2"
        caption_text = f"Giveaway pour '{prize}' lancé ! Tirage dans {args[1]}."
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=image_url,
            caption=caption_text,
            message_thread_id=message_thread_id
        )

        job_data = {"giveaway_key": giveaway_key}
        context.job_queue.run_once(draw_winners_callback, when=end_time, data=job_data, name=f"gw_draw_{giveaway_key}")
        if duration.total_seconds() > 65:
            context.job_queue.run_repeating(update_countdown_job, interval=60, first=60, data=job_data, name=f"gw_update_slow_{giveaway_key}")
            transition_time = end_time - datetime.timedelta(seconds=60)
            context.job_queue.run_once(final_minute_trigger_job, when=transition_time, data=job_data, name=f"gw_final_minute_{giveaway_key}")
        else:
            context.job_queue.run_repeating(update_countdown_job, interval=3, data=job_data, name=f"gw_update_fast_{giveaway_key}")
    except Exception as e:
        print(f"ERREUR CRITIQUE LORS DE L'ENVOI DU MESSAGE DE GIVEAWAY : {e}")
        await update.message.reply_text("Une erreur est survenue lors de la création de l'annonce.")
        if giveaway_key in active_giveaways:
            del active_giveaways[giveaway_key]

async def participate_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    giveaway_key = query.data.replace('participate_', '')
    user = query.from_user
    if giveaway_key not in active_giveaways:
        await query.answer("Désolé, ce giveaway est déjà terminé.", show_alert=True)
        return
    giveaway = active_giveaways[giveaway_key]
    required_role = giveaway.get("required_role")
    if required_role and user.id not in ADMIN_USER_IDS:
        roles = load_roles()
        if required_role not in roles or user.id not in roles[required_role]:
            await query.answer(f"Désolé, ce giveaway est réservé aux membres ayant le rôle '{required_role}'.", show_alert=True)
            return
    if user.id in giveaway['participants']: await query.answer("Vous participez déjà !", show_alert=True)
    else:
        giveaway['participants'][user.id] = user.full_name
        await query.answer("Participation enregistrée. Bonne chance !", show_alert=True)
        new_text = format_giveaway_message(giveaway_key)
        keyboard = [[InlineKeyboardButton("🎉 Participer", callback_data=query.data)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(text=new_text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN_V2)
        except Exception as e:
            if "Message is not modified" not in str(e): print(f"Ne peut pas éditer le message : {e}")

def main():
    """Lance le bot."""
    if not TOKEN:
        print("Erreur: Le token n'a pas été trouvé.")
        return
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", help_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reroll", reroll_command))
    application.add_handler(CommandHandler("giveaway", giveaway_command))
    application.add_handler(CommandHandler("annuler_giveaway", cancel_giveaway_command))
    application.add_handler(CommandHandler("assigner_role", assign_role_command))
    application.add_handler(CommandHandler("retirer_role", remove_role_command))
    application.add_handler(CallbackQueryHandler(participate_button, pattern=r'^participate_'))
    print("Le bot de giveaway (version V11 - Finition) est démarré...")
    application.run_polling()

if __name__ == '__main__':
    main()