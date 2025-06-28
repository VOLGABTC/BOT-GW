import json
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Configuration ---
# Remplace par ton token
TOKEN = '7678099516:AAFLPj57UO8NglDFAfoBKg3L3UhdsNX3D70'
# Remplace par les ID Telegram des administrateurs du bot
ADMIN_USER_IDS = [6938893387, 6619876284]
# Fichier pour stocker les données
DATA_FILE = "giveaway_data.json"

# --- Fonctions de gestion des données ---

def load_data():
    """Charge les données depuis le fichier JSON."""
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Si le fichier n'existe pas ou est vide, on retourne la structure par défaut
        return {"is_active": False, "prize": "", "participants": {}}

def save_data(data):
    """Sauvegarde les données dans le fichier JSON."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# --- Commandes du Bot ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Message d'accueil du bot."""
    await update.message.reply_text(
        "Salut ! Je suis le bot de Giveaways.\n\n"
        "Pour les admins :\n"
        "`/giveaway <description du lot>` pour lancer un concours.\n"
        "`/tirage` pour choisir un gagnant.\n"
        "`/annuler_giveaway` pour annuler.\n\n"
        "Pour tous :\n"
        "`/status` pour voir le concours en cours."
    )

async def giveaway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande pour lancer un nouveau giveaway (Admin seulement)."""
    user_id = update.effective_user.id
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("Désolé, seul un administrateur peut lancer un giveaway.")
        return

    data = load_data()
    if data['is_active']:
        await update.message.reply_text("Un giveaway est déjà en cours ! Utilisez `/tirage` ou `/annuler_giveaway` d'abord.")
        return

    # Récupère la description du lot depuis la commande
    prize = ' '.join(context.args)
    if not prize:
        await update.message.reply_text("Veuillez spécifier un lot. Usage : `/giveaway <description du lot>`")
        return

    # Met à jour les données
    data['is_active'] = True
    data['prize'] = prize
    data['participants'] = {}
    save_data(data)

    # Crée le bouton de participation
    keyboard = [[InlineKeyboardButton("🎉 Participer", callback_data='participate')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🎉 **NOUVEAU GIVEAWAY** 🎉\n\n"
        f"**Lot à gagner :** {prize}\n\n"
        f"Cliquez sur le bouton ci-dessous pour participer !",
        reply_markup=reply_markup
    )

async def participate_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère le clic sur le bouton de participation."""
    query = update.callback_query
    await query.answer()  # Indispensable pour que le bouton ne reste pas en "chargement"

    user = query.from_user
    data = load_data()

    if not data['is_active']:
        await query.edit_message_text(text="Désolé, ce giveaway est terminé.")
        return

    if str(user.id) in data['participants']:
        await query.answer(text="Vous participez déjà !", show_alert=True)
    else:
        data['participants'][str(user.id)] = user.full_name
        save_data(data)
        await query.answer(text="Votre participation a été enregistrée. Bonne chance !", show_alert=True)
        
        # Optionnel: Mettre à jour le message original pour afficher le nombre de participants
        keyboard = [[InlineKeyboardButton("🎉 Participer", callback_data='participate')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text=f"🎉 **NOUVEAU GIVEAWAY** 🎉\n\n"
                 f"**Lot à gagner :** {data['prize']}\n\n"
                 f"**Participants :** {len(data['participants'])}\n\n"
                 f"Cliquez sur le bouton ci-dessous pour participer !",
            reply_markup=reply_markup
        )


async def draw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tire au sort le gagnant (Admin seulement)."""
    user_id = update.effective_user.id
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("Désolé, seul un administrateur peut effectuer le tirage.")
        return

    data = load_data()
    if not data['is_active']:
        await update.message.reply_text("Aucun giveaway en cours.")
        return

    participants = data['participants']
    if not participants:
        await update.message.reply_text("Personne n'a participé... Le giveaway est annulé.")
    else:
        winner_id = random.choice(list(participants.keys()))
        winner_name = participants[winner_id]
        
        # Crée une mention cliquable de l'utilisateur
        winner_mention = f"[{winner_name}](tg://user?id={winner_id})"
        
        await update.message.reply_text(
            f"Le tirage est terminé !\n\n"
            f"Le lot était : **{data['prize']}**\n\n"
            f"Et le grand gagnant est... 🏆 **{winner_mention}** 🏆\n\n"
            f"Félicitations !",
            parse_mode='Markdown'
        )
    
    # Réinitialise les données
    save_data({"is_active": False, "prize": "", "participants": {}})

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annule le giveaway en cours (Admin seulement)."""
    user_id = update.effective_user.id
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("Désolé, seul un administrateur peut annuler un giveaway.")
        return
        
    save_data({"is_active": False, "prize": "", "participants": {}})
    await update.message.reply_text("Le giveaway en cours a été annulé.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le statut du giveaway en cours."""
    data = load_data()
    if not data['is_active']:
        await update.message.reply_text("Il n'y a aucun giveaway en cours pour le moment.")
    else:
        await update.message.reply_text(
            f"**Giveaway en cours :**\n"
            f"🎁 **Lot :** {data['prize']}\n"
            f"👥 **Participants :** {len(data['participants'])}"
        )


# --- Fonction Principale ---

def main():
    """Lance le bot."""
    application = ApplicationBuilder().token(TOKEN).build()

    # Commandes
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("giveaway", giveaway_command))
    application.add_handler(CommandHandler("tirage", draw_command))
    application.add_handler(CommandHandler("annuler_giveaway", cancel_command))
    application.add_handler(CommandHandler("status", status_command))
    
    # Bouton
    application.add_handler(CallbackQueryHandler(participate_button, pattern='^participate$'))

    print("Le bot de giveaway est démarré...")
    application.run_polling()


if __name__ == '__main__':
    main()