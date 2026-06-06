# Server Access & Deploy Runbook

How to connect to the production VPS and deploy. **This file contains no real hostname,
IP, username, or key.** Those live only in your local `~/.ssh/config` and your password
manager — never in the repo. The repo refers to the server only through the SSH alias
**`cbi-prod`**.

> Why: the production IP and a `root@…` login string were previously hardcoded in scripts
> and `.claude/settings.json` in a public repo (audit finding §S1). The fix is to (a) stop
> deploying as root, (b) make SSH key-only, and (c) reference the host through a local alias
> so it never appears in committed code again. See [AUDIT_FINDINGS.md](AUDIT_FINDINGS.md) §S1.

---

## 0. One-time: harden the server

Do this **today**. Run as the current `root` over your existing session.

> ⚠️ **Do not close your current root SSH session until you have confirmed a new
> `deploy` session works (step 4).** A mistake in `sshd_config` can lock you out
> otherwise. Keep one terminal connected as root the whole time.

### 1. Create a non-root deploy user

```bash
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy          # sudo for occasional admin; remove later if you want it tighter

# Let deploy manage the WordPress theme/plugins without being root:
usermod -aG www-data deploy
chgrp -R www-data /var/www/coffeebeans/wp-content/themes /var/www/coffeebeans/wp-content/plugins
chmod -R g+w     /var/www/coffeebeans/wp-content/themes /var/www/coffeebeans/wp-content/plugins
```

### 2. Install your SSH public key for `deploy`

On your **local** machine, if you don't already have a key:

```powershell
ssh-keygen -t ed25519 -C "cbi-deploy"   # press enter for defaults; set a passphrase
```

Copy the **public** key (`~/.ssh/id_ed25519.pub`) to the server's `deploy` user:

```bash
# on the server, as root:
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
# paste the contents of your local id_ed25519.pub into this file, one line:
nano /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
```

### 3. Make SSH key-only and disable root login

Create a drop-in so the change is easy to audit and revert:

```bash
cat > /etc/ssh/sshd_config.d/10-cbi-hardening.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
PermitRootLogin no
EOF

sshd -t        # MUST print nothing / exit 0. If it errors, fix before restarting.
systemctl restart ssh
```

### 4. Verify before you disconnect

From your **local** machine, in a **new** terminal (leave the root session open):

```powershell
ssh deploy@<YOUR_SERVER_IP>     # should log in with your key, no password
sudo whoami                     # should print: root  (confirms sudo works)
```

If that works, you can close the old root session. If it doesn't, fix it from the
still-open root session (revert `/etc/ssh/sshd_config.d/10-cbi-hardening.conf` and
`systemctl restart ssh`).

---

## 5. One-time: local SSH alias

On your **local** machine, add this to `~/.ssh/config` (create the file if missing).
**This is the only place the real IP lives.** Do not commit it.

```sshconfig
Host cbi-prod
    HostName <YOUR_SERVER_IP>
    User deploy
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

Test: `ssh cbi-prod "whoami"` → `deploy`.

Now every script and command in this repo that says `cbi-prod` just works, and the IP
is never in the repo. `reformat_origin_descriptions.py` reads the host from the
`CBI_SSH_HOST` env var and defaults to `cbi-prod`, so it needs no edit.

---

## 6. Deploying theme / plugin changes

There is no CI deploy. Push files with `scp` over the alias, then flush cache. Examples
(run from the repo root, PowerShell):

```powershell
# Theme files
scp "wordpress-plugins/coffeebeanindex-theme/style.css"     cbi-prod:/var/www/coffeebeans/wp-content/themes/coffeebeanindex/style.css
scp "wordpress-plugins/coffeebeanindex-theme/functions.php" cbi-prod:/var/www/coffeebeans/wp-content/themes/coffeebeanindex/functions.php

# Flush WordPress cache (run wp as the web user, not root)
ssh cbi-prod "sudo -u www-data wp cache flush --path=/var/www/coffeebeans"
```

> The allow-listed deploy commands in `.claude/settings.json` now use the `cbi-prod`
> alias instead of a `root@<ip>` string. After hardening, prefer `sudo -u www-data wp …`
> over `wp … --allow-root` (the latter only mattered when running as root).

## 7. Running the publish pipeline on the server

```bash
ssh cbi-prod
# then, on the server:
sudo -u www-data wp --path=/var/www/coffeebeans eval-file /opt/scrapers/create_beans.php
/opt/venv/bin/python3 /opt/scrapers/generate_review.py <product-id>
sudo -u www-data wp --path=/var/www/coffeebeans eval-file /opt/scrapers/push_drafts.php
```

(`create_beans.php` is the canonical importer — not `create_beans_wpcli.sh`, which was
removed. See [AUDIT_FINDINGS.md](AUDIT_FINDINGS.md) §R2.)

---

## 8. Optional: scrub the IP from git history

This is **cleanup, not the fix** — the IP is already public (scraped/indexed), so host
hardening above is what actually protects you. If you still want a clean history:

```bash
pip install git-filter-repo
git filter-repo --replace-text <(printf '%s==>cbi-prod\n' '<OLD_IP_HERE>')
git push --force-with-lease --all
```

Force-pushing rewrites history for everyone — coordinate if anyone else has clones.

## 9. Stronger options (consider)

- **Provider firewall:** restrict SSH (port 22) to your home/office IP at the Cloud
  firewall level, so the exposed IP is unreachable for SSH from anywhere else.
- **Rotate the host:** since the old IP is public, a floating IP / rebuild on a new IP
  closes the book on the leaked address entirely (combine with the firewall above).
- **fail2ban** is already installed by `setup.sh`; confirm the `sshd` jail is active
  (`fail2ban-client status sshd`).

---

## Quick reference

| Task | Command |
|---|---|
| Connect | `ssh cbi-prod` |
| Deploy a theme file | `scp <local> cbi-prod:/var/www/coffeebeans/wp-content/themes/coffeebeanindex/<file>` |
| Flush cache | `ssh cbi-prod "sudo -u www-data wp cache flush --path=/var/www/coffeebeans"` |
| Tail scraper log | `ssh cbi-prod "tail -n 50 /opt/data/scraper.log"` |
| Tail alert log | `ssh cbi-prod "tail -n 50 /opt/data/alerts.log"` |
