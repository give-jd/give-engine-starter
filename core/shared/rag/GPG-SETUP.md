# GPG keypair Gi.Ve — setup produzione libreria preindicizzata

Procedura per generare la keypair GPG ufficiale Gi.Ve che firma le skill
distribuite via CDN `cdn.givegroup.it/atheneo-library/`. Documento
operativo per il primo release commerciale di Atheneo Light v0.2+.

## 1. Generare keypair offline

Su macchina dedicata, offline o air-gapped quando possibile.

```bash
export GNUPGHOME=~/.atheneo-signing-key
mkdir -p $GNUPGHOME
chmod 700 $GNUPGHOME

cat > /tmp/keygen.batch <<EOF
%echo Generating Atheneo signing key
Key-Type: RSA
Key-Length: 4096
Key-Usage: sign
Name-Real: GI.VE GROUP S.R.L. - Atheneo Library
Name-Email: atheneo-signing@givegroup.it
Expire-Date: 5y
Passphrase: <CAMBIA QUESTA STRINGA, salva in password manager>
%commit
%echo Done
EOF

gpg --batch --generate-key /tmp/keygen.batch
shred -u /tmp/keygen.batch
```

Verifica fingerprint:

```bash
gpg --list-keys --keyid-format LONG --with-fingerprint atheneo-signing@givegroup.it
```

Annota la fingerprint sul registro chiavi interno + pubblicala su sito.

## 2. Backup offline

```bash
gpg --armor --export atheneo-signing@givegroup.it > atheneo-signing.pub.asc
gpg --armor --export-secret-keys atheneo-signing@givegroup.it > atheneo-signing.priv.asc
gpg --output atheneo-signing.revoke.asc --gen-revoke atheneo-signing@givegroup.it
```

Conserva:
- `atheneo-signing.pub.asc` → committato nel monorepo, distribuito agli
  utenti via installer
- `atheneo-signing.priv.asc` → su 2 USB hardware criptati, in cassaforte
- `atheneo-signing.revoke.asc` → USB separato dal privato

Mai committare `priv.asc` nel monorepo o cloud sync.

## 3. Distribuzione chiave pubblica

Pubblica:
- `engine.givegroup.it/.well-known/atheneo-signing.pub.asc`
- README del repo `give-engine` (sezione Sicurezza)
- Pagina `/recipes/atheneo-light` (FAQ "Firma libreria")

Installer Gi.Ve Engine importa automaticamente la chiave al primo avvio:

```bash
curl -fsSL https://engine.givegroup.it/.well-known/atheneo-signing.pub.asc \
  | gpg --import
```

## 4. Firmare una skill

```bash
gpg --armor --detach-sign \
  --default-key atheneo-signing@givegroup.it \
  --output manuali-anthropic-2026-W22.atheneo-light.sig \
  manuali-anthropic-2026-W22.atheneo-light
```

Il manifest pubblico (`library_manifest.json`) include la firma
ASCII-armored nel campo `signature` di ogni skill (sostituisce
`STUB-NOT-VERIFIED-V0.1`).

## 5. Verifica utente finale

Atheneo Light v0.2+ con `signature_mode="strict"` (default produzione)
chiama `gpg --verify` sull'archive scaricato contro la firma ricevuta.
Solo firme verificate dal keyring locale dell'utente passano.

## 6. Rotazione chiave

Rotazione consigliata ogni 2 anni (Expire-Date 5y lascia margine):

1. Genera nuova keypair con metodo (1) sopra
2. Cross-sign nuova con la vecchia: `gpg --default-key OLD_FP --sign-key NEW_FP`
3. Pubblica nuova nei canali (2)
4. Re-firma skill esistenti con nuova
5. Ritira vecchia dopo 6 mesi di overlap

## Coerenza con Punti cardine

- **Punto 14**: verifica gira localmente sul PC dell'utente. Nessuna
  chiamata a Gi.Ve per validare una firma.
- **Punto 22**: chiave privata Gi.Ve resta su supporti hardware Gi.Ve.
  Chiave pubblica self-hosted dal monorepo. Nessun managed signing service.
