"""Envia e-mail pelo SMTP do Gmail (senha de app) quando há projetos aprovados."""
import html
import logging
import smtplib
from email.message import EmailMessage

from config import carregar_segredos

log = logging.getLogger("notificador")


def _credenciais():
    s = carregar_segredos()
    usuario, senha = s.get("gmail_usuario"), s.get("gmail_senha_app")
    if not usuario or not senha or "seu.email" in usuario:
        return None
    return usuario, senha.replace(" ", ""), s.get("email_destino") or usuario


def enviar(assunto: str, texto: str, corpo_html: str) -> bool:
    cred = _credenciais()
    if not cred:
        log.warning("E-mail não configurado (config/segredos.json); notificação não enviada.")
        return False
    usuario, senha, destino = cred
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = assunto, usuario, destino
    msg.set_content(texto)
    msg.add_alternative(corpo_html, subtype="html")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(usuario, senha)
            smtp.send_message(msg)
        log.info("E-mail enviado para %s", destino)
        return True
    except Exception as e:
        log.error("Falha ao enviar e-mail: %s", e)
        return False


def notificar_aprovados(cfg: dict, projetos: list[dict]) -> bool:
    if not projetos:
        return False
    painel = f"http://{cfg['painel']['host']}:{cfg['painel']['porta']}"
    assunto = f"[Freelance bot] {len(projetos)} projeto(s) novo(s) aprovado(s)"
    linhas = [f"- [{p['nota_total']:.0f}] {p['titulo']} ({p['plataforma']}) {painel}/projeto/{p['id']}"
              for p in projetos]
    texto = "Projetos aprovados nesta rodada:\n\n" + "\n".join(linhas) + f"\n\nPainel: {painel}/?status=novo"
    itens = "".join(
        f"<li><b>{p['nota_total']:.0f}</b> · <a href='{painel}/projeto/{p['id']}'>{html.escape(p['titulo'])}</a>"
        f" <small>({html.escape(p['plataforma'])})</small></li>" for p in projetos)
    corpo = (f"<p>Projetos aprovados nesta rodada:</p><ul>{itens}</ul>"
             f"<p><a href='{painel}/?status=novo'>Abrir o painel</a> "
             f"(o painel precisa estar rodando neste computador)</p>")
    return enviar(assunto, texto, corpo)
