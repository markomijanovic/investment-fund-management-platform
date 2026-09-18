# Vodič za odbranu projekta

## Projekat u jednoj rečenici

Zaposleni predlaže BUY ili SELL nalog, direktor za taj nalog pokreće blockchain glasanje, ovlašćeni glasači odlučuju, a Kubernetes CronJob prenosi konačan rezultat u MongoDB.

```text
klijent → auth → MySQL
klijent → employee → Redis (nalozi) + MongoDB (imovina)
klijent → director → Redis + Ganache/Solidity
Kubernetes CronJob → ugovor → MongoDB + čišćenje Redis stanja
```

## Komponente

| Komponenta | Odgovornost |
|---|---|
| Auth servis | registracija, prijava, brisanje korisnika i izdavanje JWT-a |
| Employee servis | pretraga imovine i pravljenje BUY/SELL naloga |
| Director servis | pregled naloga, pokretanje glasanja i finansijski izveštaj |
| MySQL | korisnici, lozinke u hash obliku i uloge |
| MongoDB | kupljena/prodata imovina i evidencija obrađenih glasanja |
| Redis | privremeni nalozi i metapodaci aktivnih glasanja |
| Ganache | lokalna Ethereum mreža na kojoj se izvršava ugovor |
| `sql-init` Job | jednom kreira SQL tabele i početnog direktora |
| `contract-checker` CronJob | svakog minuta proverava završena glasanja i primenjuje rezultat |

## Tok kroz servise

### 1. Autentikacija

- `POST /register` validira podatke i pravi korisnika sa ulogom `employee`.
- `POST /login` proverava hash lozinke i vraća JWT sa identitetom i ulogom.
- `POST /delete` briše trenutno prijavljenog korisnika.
- Employee i director rute proveravaju JWT i zahtevanu ulogu dekoratorom `role_required`.

Korisnici pripadaju MySQL-u jer su strukturisani, email mora biti jedinstven, a upis je transakcioni.

### 2. Employee servis

- `POST /search` pretražuje MongoDB po nazivu, kategoriji, datumima i dinamičkim `info` filterima.
- `POST /create_buy_order` proverava naziv, kategorije, cenu i dodatne informacije, pa nalog smešta u Redis.
- `POST /create_sell_order` prvo proverava da imovina postoji u MongoDB, pa SELL nalog smešta u Redis.

Redis je ovde red/privremeno stanje: nalog još nije konačna imovina i zato se ne upisuje odmah u MongoDB.

### 3. Director servis

- `GET /pending_orders` čita neobrađene naloge iz Redis-a.
- `POST /decision` prima UUID naloga i neparan spisak jedinstvenih Ethereum adresa.
- Servis deploy-uje novi `InvestmentVote` ugovor i vraća tri nepotpisane transakcije: `approve_transaction`, `reject_transaction` i `veto_transaction`.
- `GET /report` MongoDB agregacijom računa potrošeno i zarađeno po kategoriji.

Transakcije su nepotpisane zato što glasač treba da ih pošalje sa svog Ethereum naloga. Privatni ključevi ne pripadaju serverskoj aplikaciji.

## Kako se glasanje završava

Za `n` glasača prag je `n / 2 + 1`. Pošto direktor prihvata samo neparan broj glasača, ne može nastati nerešen ishod.

- Kada `approveVotes` dostigne prag: `ended = true`, `approved = true`.
- Kada `rejectVotes` dostigne prag: `ended = true`, `approved` ostaje `false`.
- Kada direktor pozove `veto()`: `ended = true`, `vetoed = true`, ugovor nema poslovni efekat.

Za svaku akciju važi `votingActive`, pa posle završetka nema daljeg glasanja ni veta. Običan glas može poslati samo adresa iz `allowedVoters`, i to samo jednom zbog `hasVoted`. Veto može poslati samo `director`, odnosno adresa koja je deploy-ovala ugovor. Ugovor nema vremenski timeout: završava se većinom ili vetom.

## Šta radi contract checker

1. Iz Redis-a uzima UUID-e aktivnih glasanja.
2. Za svaki nalog uzima kratak Redis lock da dva checker-a ne obrade isti nalog paralelno.
3. Sa ugovora čita `ended`, `approved` i `vetoed`.
4. Ako glasanje traje, ne menja ništa.
5. Ako je odobren BUY, dodaje imovinu u MongoDB.
6. Ako je odobren SELL, upisuje prodajnu cenu i datum u postojeću imovinu.
7. Ako je REJECTED ili VETOED, ne menja imovinu.
8. Ishod beleži u `processed_votes`, pa je obrada idempotentna čak i ako se Job ponovi.
9. Na kraju uklanja nalog i aktivno glasanje iz Redis-a.

CronJob se normalno izvršava jednom u minuti i završava sa statusom `Completed`. To nije greška: Job pod treba da obavi posao i izađe.

## Zašto četiri sistema za podatke

- **MySQL**: relacijski korisnici, jedinstven email i pouzdane transakcije.
- **MongoDB**: fleksibilan `info` objekat imovine, filteri i agregacioni izveštaj.
- **Redis**: brzo privremeno stanje naloga, glasanja i lock-ova.
- **Blockchain**: odluka se izvršava pravilima ugovora i rezultat se ne menja proizvoljno u API-ju.

## Kubernetes deo

Sve što pripada aplikaciji nalazi se u `k8s/all.yaml`:

- jedan namespace `iep`;
- ConfigMap za običnu konfiguraciju i Secret za lozinke;
- StatefulSet + PVC za MySQL i MongoDB;
- Deployment za Redis i Ganache;
- Deployment + Service za auth, employee i director;
- tri employee replike radi horizontalnog skaliranja;
- SQL `Job` za jednokratnu inicijalizaciju;
- `CronJob` za proveru ugovora svakog minuta.

`imagePullPolicy: IfNotPresent` omogućava lokalnom Docker Desktop Kubernetes klasteru da koristi prethodno izgrađene `iep-*` image-e. Zato na odbrani ne treba registry ako su image-i napravljeni unapred i klaster nije resetovan.

## Dockerfile

Jedan višefazni Dockerfile deli zajednički `base` sloj, a ima četiri cilja:

- `auth`, `employee` i `director` pokreću odgovarajući Gunicorn servis;
- `checker` pokreće Python modul za proveru ugovora.

Zato skripta gradi `iep-auth`, `iep-employee`, `iep-director` i `iep-checker` iz istog repozitorijuma, ali svaki image ima svoju startnu komandu.

## Predlog demonstracije na odbrani

1. Pre odbrane, dok ima interneta, pokreni `setup`.
2. Pokreni `start --clean` i pokaži da su podovi `Running`, a Job `Completed`.
3. Pokreni `test --reset` i pokaži rezultat gradera.
4. Objasni jedan BUY tok: employee → Redis → director → ugovor → checker → MongoDB.
5. U Solidity kodu pokaži `threshold`, `votingActive`, `_castVote` i `veto`.
6. U manifestu pokaži SQL Job, CronJob i tri employee replike.

Na macOS/Linux komandama prethodi `./`, a na Windows PowerShell-u `.\`; `kubectl` komande su iste na oba sistema.

## Kratka pitanja koja možeš očekivati

**Zašto Job za SQL inicijalizaciju?**  
To je konačan jednokratni zadatak. Kubernetes može da prati da li je uspešno završen i da ga ponovi pri grešci.

**Zašto CronJob za proveru ugovora?**  
Provera je periodičan posao, ne stalni HTTP servis. CronJob na rasporedu pravi Job koji proveri stanje i izađe.

**Zašto je `Completed` ispravan status?**  
Job i CronJob podovi nisu serveri. Uspešan izlazak procesa znači da je njihov posao završen.

**Zašto checker koristi lock i `processed_votes`?**  
Lock sprečava paralelnu obradu, a trajni marker sprečava duplu poslovnu promenu ako se obrada ponovi.

**Zašto `setuptools==70.3.0` u grader venv-u?**  
Profesorov Web3 paket koristi stari modul `pkg_resources`. Setuptools ga obezbeđuje, a fiksna kompatibilna verzija sprečava da novija promena pokvari stare testove.

**Zašto ne gasiti ili resetovati Kubernetes pred odbranu?**  
Reset klastera može obrisati lokalno učitane image-e i ponovo zatražiti preuzimanje sistemskih image-a. Unapred pripremljen klaster radi bez interneta.

**Kako tražiš uzrok `CrashLoopBackOff`?**  
Prvo `kubectl logs POD -n iep`, zatim `kubectl describe pod POD -n iep`, pa proverim konfiguraciju, zavisne servise i image.

