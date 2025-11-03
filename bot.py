import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import random
import string
import asyncio
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# -----------------------------
# CONFIGURACIÓN DEL BOT
# -----------------------------
load_dotenv()
TOKEN = os.getenv("TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

ROL_AUTORIZADO_SUELDOS = 1433817220336582847  # Rol autorizado para configurar sueldos
ROL_AUTORIZADO_TIENDA = 1433817220336582847    # Rol autorizado para añadir artículos a la tienda

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# -----------------------------
# BASE DE DATOS
# -----------------------------
def conectar():
    return sqlite3.connect("dni.db")

def crear_tablas():
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dni (
                user_id INTEGER,
                nombre TEXT,
                edad INTEGER,
                genero TEXT,
                numero_dni TEXT,
                tipo TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS economia (
                user_id INTEGER PRIMARY KEY,
                dinero INTEGER DEFAULT 0,
                ultimo_cobro TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sueldos (
                rol_id INTEGER PRIMARY KEY,
                cantidad INTEGER,
                dias INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tienda (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                precio INTEGER,
                rol_id INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventario (
                user_id INTEGER,
                item_id INTEGER,
                FOREIGN KEY (item_id) REFERENCES tienda(id)
            )
        """)
        conn.commit()

crear_tablas()

# -----------------------------
# FUNCIONES AUXILIARES
# -----------------------------
def generar_dni():
    letras = ''.join(random.choices(string.ascii_uppercase, k=3))
    numeros = ''.join(random.choices(string.digits, k=5))
    return f"{letras}-{numeros}"

def obtener_dinero(user_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT dinero FROM economia WHERE user_id = ?", (user_id,))
    resultado = cursor.fetchone()
    conn.close()
    return resultado[0] if resultado else 0

def actualizar_dinero(user_id, cantidad):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT dinero FROM economia WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        cursor.execute("UPDATE economia SET dinero = dinero + ? WHERE user_id = ?", (cantidad, user_id))
    else:
        cursor.execute("INSERT INTO economia (user_id, dinero, ultimo_cobro) VALUES (?, ?, ?)", (user_id, cantidad, None))
    conn.commit()
    conn.close()

async def init_db():
    await asyncio.to_thread(crear_tablas)

# -----------------------------
# EVENTO ON_READY
# -----------------------------
@bot.event
async def on_ready():
    await init_db()
    try:
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"✅ Comandos registrados correctamente ({len(synced)}) en el servidor {GUILD_ID}")
        else:
            synced = await bot.tree.sync()
            print(f"🌍 Comandos registrados globalmente ({len(synced)}) comandos.")
    except Exception as e:
        print(f"❌ Error al registrar comandos: {e}")
    print(f"🤖 Bot conectado como {bot.user}")

# -----------------------------
# COMANDOS DE DNI
# -----------------------------
@bot.tree.command(name="registrar", description="Regístrate y obtén tu DNI oficial")
async def registrar(interaction: discord.Interaction, nombre: str, edad: int, genero: str):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM dni WHERE user_id = ? AND tipo = 'principal'", (interaction.user.id,))
    if cursor.fetchone():
        await interaction.response.send_message("⚠️ Ya tienes un DNI principal registrado.", ephemeral=True)
        conn.close()
        return
    numero_dni = generar_dni()
    cursor.execute(
        "INSERT INTO dni (user_id, nombre, edad, genero, numero_dni, tipo) VALUES (?, ?, ?, ?, ?, ?)",
        (interaction.user.id, nombre, edad, genero, numero_dni, "principal")
    )
    conn.commit()
    conn.close()
    embed = discord.Embed(title="🪪 DNI — Bilbao RP Oficial", color=discord.Color.blue())
    embed.add_field(name="👤 Nombre", value=nombre)
    embed.add_field(name="🎂 Edad", value=str(edad))
    embed.add_field(name="⚧ Género", value=genero)
    embed.add_field(name="🔢 Número de DNI", value=numero_dni)
    embed.set_footer(text="Bilbao RP — Oficial")
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

# -----------------------------
# SISTEMA DE ECONOMÍA
# -----------------------------
@bot.tree.command(name="setsueldo", description="Configura el sueldo de un rol (solo rol autorizado)")
async def setsueldo(interaction: discord.Interaction, rol: discord.Role, cantidad: int, dias: int):
    if ROL_AUTORIZADO_SUELDOS not in [r.id for r in interaction.user.roles]:
        await interaction.response.send_message("❌ No tienes permiso para usar este comando.", ephemeral=True)
        return

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO sueldos (rol_id, cantidad, dias) VALUES (?, ?, ?)", (rol.id, cantidad, dias))
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"✅ Sueldo configurado para {rol.mention}: {cantidad} 💵 cada {dias} días.")

@bot.tree.command(name="cobrar_sueldo", description="Cobra tu sueldo si ya puedes hacerlo")
async def cobrar_sueldo(interaction: discord.Interaction):
    usuario = interaction.user
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT dinero, ultimo_cobro FROM economia WHERE user_id = ?", (usuario.id,))
    data = cursor.fetchone()
    ahora = datetime.now()

    roles_usuario = [r.id for r in usuario.roles]
    cursor.execute("SELECT rol_id, cantidad, dias FROM sueldos")
    sueldos = cursor.fetchall()

    sueldo_elegible = None
    for rol_id, cantidad, dias in sueldos:
        if rol_id in roles_usuario:
            sueldo_elegible = (cantidad, dias)
            break

    if not sueldo_elegible:
        await interaction.response.send_message("❌ No tienes un rol con sueldo asignado.", ephemeral=True)
        conn.close()
        return

    cantidad, dias = sueldo_elegible
    if data and data[1]:
        ultimo = datetime.fromisoformat(data[1])
        if ahora < ultimo + timedelta(days=dias):
            faltan = (ultimo + timedelta(days=dias)) - ahora
            await interaction.response.send_message(f"⏳ Aún no puedes cobrar. Faltan {faltan.days} días.", ephemeral=True)
            conn.close()
            return

    actualizar_dinero(usuario.id, cantidad)
    cursor.execute("UPDATE economia SET ultimo_cobro = ? WHERE user_id = ?", (ahora.isoformat(), usuario.id))
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"✅ Has cobrado {cantidad} 💵. ¡Buen trabajo!")

@bot.tree.command(name="saldo", description="Consulta tu saldo actual")
async def saldo(interaction: discord.Interaction):
    dinero = obtener_dinero(interaction.user.id)
    await interaction.response.send_message(f"💰 Tu saldo actual es: **{dinero}** 💵")

# -----------------------------
# 🎰 CASINO - RULETA
# -----------------------------
@bot.tree.command(name="ruleta", description="Apuesta dinero en la ruleta 🎯")
@app_commands.describe(
    cantidad="Cantidad de dinero a apostar",
    apuesta="Tu apuesta: rojo, negro o un número del 0 al 36"
)
async def ruleta(interaction: discord.Interaction, cantidad: int, apuesta: str):
    user = interaction.user
    saldo_actual = obtener_dinero(user.id)

    # Validaciones
    if cantidad <= 0:
        await interaction.response.send_message("❌ La cantidad debe ser mayor que 0.", ephemeral=True)
        return
    if saldo_actual < cantidad:
        await interaction.response.send_message("💸 No tienes suficiente dinero para apostar.", ephemeral=True)
        return

    # Normalizamos la apuesta
    apuesta = apuesta.lower()
    colores = ["rojo", "negro"]
    numeros_validos = [str(i) for i in range(0, 37)]

    if apuesta not in colores and apuesta not in numeros_validos:
        await interaction.response.send_message(
            "⚠️ Apuesta inválida. Usa `rojo`, `negro` o un número entre 0 y 36.",
            ephemeral=True
        )
        return

    # Simulación de la ruleta 🎡
    import random
    numero_salida = random.randint(0, 36)
    color_salida = "rojo" if numero_salida % 2 == 0 else "negro" if numero_salida != 0 else "verde"

    resultado_texto = f"🎡 La ruleta gira... ¡y cae en **{numero_salida} ({color_salida})**!"

    # Verificamos si gana
    if apuesta == color_salida:
        ganancia = cantidad  # x2 total
        actualizar_dinero(user.id, ganancia)
        await interaction.response.send_message(
            f"{resultado_texto}\n\n🟥 ¡Has ganado {ganancia}💵 apostando al color **{apuesta}**!",
            ephemeral=False
        )
    elif apuesta == str(numero_salida):
        ganancia = cantidad * 9  # x10 total
        actualizar_dinero(user.id, ganancia)
        await interaction.response.send_message(
            f"{resultado_texto}\n\n🎯 ¡Número exacto! Ganaste **{ganancia}💵** apostando al **{apuesta}**.",
            ephemeral=False
        )
    else:
        actualizar_dinero(user.id, -cantidad)
        await interaction.response.send_message(
            f"{resultado_texto}\n\n💀 Has perdido tu apuesta de **{cantidad}💵**.",
            ephemeral=False
        )

# -----------------------------
# SISTEMA DE TIENDA 🛒
# -----------------------------
ROL_AUTORIZADO_TIENDA = 1433817220336582847  # ID del rol autorizado para gestionar la tienda

@bot.tree.command(name="additem", description="Añade un artículo a la tienda (solo rol autorizado)")
async def additem(interaction: discord.Interaction, nombre: str, precio: int, rol: discord.Role):
    """Permite a los usuarios con rol autorizado añadir ítems a la tienda"""
    if ROL_AUTORIZADO_TIENDA not in [r.id for r in interaction.user.roles]:
        await interaction.response.send_message("❌ No tienes permiso para añadir artículos.", ephemeral=True)
        return

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tienda (nombre, precio, rol_id) VALUES (?, ?, ?)", (nombre, precio, rol.id))
    conn.commit()
    conn.close()

    await interaction.response.send_message(
        f"✅ Artículo **{nombre}** añadido a la tienda por {precio}💵 (rol otorgado: {rol.mention}).",
        ephemeral=True
    )

# -----------------------------
# TIENDA CON MENÚ INTERACTIVO
# -----------------------------
@bot.tree.command(name="tienda", description="Abre la tienda y compra desde un menú 🛒")
async def tienda(interaction: discord.Interaction):
    """Muestra el menú desplegable de la tienda para comprar artículos"""
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, precio, rol_id FROM tienda")
    items = cursor.fetchall()
    conn.close()

    if not items:
        await interaction.response.send_message("🛒 No hay artículos en la tienda por ahora.", ephemeral=True)
        return

    # Creamos las opciones para el menú desplegable
    options = [
        discord.SelectOption(label=f"{nombre}", description=f"Precio: {precio}💵", value=str(id))
        for id, nombre, precio, rol_id in items
    ]

    class MenuCompra(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)

            self.select_menu = discord.ui.Select(
                placeholder="Selecciona un artículo para comprar 🛍️",
                options=options
            )
            self.select_menu.callback = self.select_callback
            self.add_item(self.select_menu)

        async def select_callback(self, interaction2: discord.Interaction):
            item_id = int(self.select_menu.values[0])

            conn = conectar()
            cursor = conn.cursor()
            cursor.execute("SELECT nombre, precio, rol_id FROM tienda WHERE id = ?", (item_id,))
            item = cursor.fetchone()
            conn.close()

            if not item:
                await interaction2.response.send_message("❌ El ítem ya no existe.", ephemeral=True)
                return

            nombre, precio, rol_id = item
            dinero_actual = obtener_dinero(interaction2.user.id)

            if dinero_actual < precio:
                await interaction2.response.send_message(
                    f"💸 No tienes suficiente dinero para comprar **{nombre}**.",
                    ephemeral=True
                )
                return

            # Restamos el dinero
            actualizar_dinero(interaction2.user.id, -precio)

            # Guardamos en inventario
            conn = conectar()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventario (
                    user_id INTEGER,
                    item_id INTEGER
                )
            """)
            cursor.execute("INSERT INTO inventario (user_id, item_id) VALUES (?, ?)", (interaction2.user.id, item_id))
            conn.commit()
            conn.close()

            # Asignamos el rol asociado
            rol = interaction2.guild.get_role(rol_id)
            if rol:
                await interaction2.user.add_roles(rol)

            await interaction2.response.send_message(
                f"✅ Has comprado **{nombre}** por {precio}💵 y recibiste el rol {rol.mention}.",
                ephemeral=True
            )

    # Embed visual
    embed = discord.Embed(
        title="🛍️ Tienda de Bilbao RP",
        description="Selecciona un artículo del menú para comprarlo.",
        color=discord.Color.green()
    )

    for id, nombre, precio, rol_id in items:
        embed.add_field(name=f"{nombre}", value=f"💵 {precio}", inline=True)

    view = MenuCompra()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# -----------------------------
# QUITAR ITEM (solo roles autorizados)
# -----------------------------
ROLES_AUTORIZADOS_RETIRO = [1433817220336582847,1433817220336582842,1433817220336582838,1433817220336582841,1433817219971809423,1433817220336582840,1433817220336582839]

@bot.tree.command(name="quitar_item_usuario", description="Quita un item (rol) a un usuario — solo roles autorizados")
@app_commands.describe(usuario="Usuario objetivo", rol="Rol (item) a quitar del usuario")
async def quitar_item_usuario(interaction: discord.Interaction, usuario: discord.Member, rol: discord.Role):
    ejecutor_roles = [r.id for r in interaction.user.roles]
    if not any(rid in ROLES_AUTORIZADOS_RETIRO for rid in ejecutor_roles):
        await interaction.response.send_message("❌ No tienes permisos para ejecutar este comando.", ephemeral=True)
        return

    if rol.id not in [r.id for r in usuario.roles]:
        await interaction.response.send_message(f"⚠️ {usuario.mention} no tiene el rol {rol.mention}.", ephemeral=True)
        return

    try:
        await usuario.remove_roles(rol, reason=f"Quitar item por {interaction.user}")
    except Exception:
        await interaction.response.send_message("❌ No pude quitar el rol. Revisa jerarquía/permisos del bot.", ephemeral=True)
        return

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT nombre FROM tienda WHERE rol_id = ?", (rol.id,))
    item = cursor.fetchone()
    conn.close()

    nombre = item[0] if item else rol.name
    await interaction.response.send_message(f"🗑️ {usuario.mention} perdió el ítem **{nombre}** ({rol.mention}).")

# -----------------------------
# INICIAR BOT
# -----------------------------
bot.run(TOKEN)
