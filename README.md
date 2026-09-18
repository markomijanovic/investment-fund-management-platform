# IEP projekat — investicioni fond

Mikroservisna Flask aplikacija za upravljanje investicionim fondom, pokrenuta u lokalnom Kubernetes klasteru. Zaposleni predlažu kupovinu ili prodaju imovine, direktor pokreće glasanje na Ethereum ugovoru, a periodični checker rezultat prenosi u MongoDB.

## Šta je implementirano

- autentikacija i JWT uloge `employee` i `director`;
- pretraga imovine i BUY/SELL nalozi;
- glasanje na Solidity ugovoru: `approve`, `reject` i direktorski `veto`;
- MySQL inicijalizacija kroz Kubernetes `Job`;
- provera ugovora i ažuriranje MongoDB kroz Kubernetes `CronJob`;
- tri replike employee servisa;
- trajni MySQL i MongoDB podaci kroz PVC;
- originalni profesorovi testovi bez izmena — poslednja provera: **179/179 bodova**.

Za učenje projekta od početka koristi [docs/DETALJNO_OBJASNJENJE_PROJEKTA.md](docs/DETALJNO_OBJASNJENJE_PROJEKTA.md). Za kratak pregled i pitanja pročitaj [docs/ODBRANA.md](docs/ODBRANA.md), a ako nešto zakaže na odbrani koristi [docs/PROBLEMI_NA_ODBRANI.md](docs/PROBLEMI_NA_ODBRANI.md). Primeri mogućih zadataka sa MongoDB, MySQL i Redis bazom nalaze se u [docs/MODIFIKACIJE_BAZE.md](docs/MODIFIKACIJE_BAZE.md).

## Struktura

```text
blockchain/       Solidity ugovor i kompajlirani artifact
common/           konfiguracija, JWT, klijenti i zajedničke funkcije
jobs/             periodična provera završenih glasanja
k8s/all.yaml      kompletna Kubernetes definicija aplikacije
professor_tests/  originalni profesorov grader
services/         auth, employee i director mikroservisi
scripts/          automatizacija za pokretanje, reset i testiranje
tests/            interni brzi testovi
```

## Portovi

| Servis | Lokalni URL |
|---|---|
| Auth | `http://127.0.0.1:5000` |
| Employee | `http://127.0.0.1:5001` |
| Director | `http://127.0.0.1:5002` |
| Ganache | `http://127.0.0.1:8545` |

## macOS / Linux

Dok imaš internet, jednom pripremi image-e i grader:

```bash
./setup.sh
```

Pokretanje aplikacije i profesorovih testova:

```bash
./start.sh --clean
./test.sh --reset
```

Kasnije koristi `./start.sh` bez brisanja podataka. Posle izmene izvornog koda koristi `./start.sh --build`.

## Windows PowerShell

Ako je izvršavanje lokalnih skripti blokirano, jednom u tom terminalu pokreni:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Zatim:

```powershell
.\setup.ps1
.\start.ps1 -Clean
.\test.ps1 -Reset
```

Docker Desktop mora koristiti Linux containers i Kubernetes mora biti uključen.

## Šta rade skripte

- `setup` preuzima infrastrukturne image-e, gradi četiri lokalna image-a i priprema grader venv; internet je potreban samo tada.
- `start` primenjuje `k8s/all.yaml`, čeka baze, SQL Job i servise; ako image-i postoje, ne gradi ih ponovo.
- `test --reset` vraća testne podatke u početno stanje, privremeno otvara potrebne portove i pokreće neizmenjene profesorove testove.

## Korisne komande

```bash
kubectl get pods,services,jobs,cronjobs -n iep
kubectl logs job/sql-init -n iep
kubectl logs -l app=contract-checker -n iep --tail=50
kubectl logs deployment/director -n iep --tail=50
kubectl describe pod IME_PODA -n iep
```

Direktor se inicijalizuje kroz SQL Job:

```text
email:    onlymoney@gmail.com
password: evenmoremoney
```

Interni testovi, nezavisni od pokrenutog klastera:

```bash
.venv/bin/python -m pytest -q tests
```
