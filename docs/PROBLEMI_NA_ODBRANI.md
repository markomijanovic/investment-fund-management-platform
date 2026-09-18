# Problemi na odbrani — brza dijagnostika i popravka

Ovaj dokument koristi kada nešto ne radi. Nemoj nasumično brisati klaster, namespace ili image-e: prvo pronađi tačan uzrok. Komande `kubectl` su iste na macOS-u i Windowsu; razlikuju se samo komande za pokretanje skripti.

## Najkraći plan za odbranu

### Pre dolaska, dok imaš internet

macOS/Linux:

```bash
cd /putanja/do/iep_projekat
./setup.sh
./start.sh --clean
./test.sh --reset
```

Windows PowerShell:

```powershell
cd C:\putanja\do\iep_projekat
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
.\start.ps1 -Clean
.\test.ps1 -Reset
```

Moraš dobiti **179/179**. Zatim proveri:

```bash
docker image inspect iep-auth:latest
docker image inspect iep-employee:latest
docker image inspect iep-director:latest
docker image inspect iep-checker:latest
kubectl get pods,jobs,cronjobs -n iep
```

Očekivano je:

- auth, employee, director, MySQL, MongoDB, Redis i Ganache su `Running`;
- sve aplikacione replike imaju `READY 1/1`;
- `sql-init` je `Completed`;
- stari contract-checker podovi su `Completed`;
- CronJob `contract-checker` postoji.

Posle uspešne provere ne menjaj Kubernetes verziju, broj node-ova, container runtime niti Docker Desktop podešavanja. To može resetovati klaster i obrisati lokalni cache image-a.

### Na samoj odbrani

Ako je aplikacija već pokrenuta, prvo probaj samo:

```bash
kubectl get pods -n iep
./test.sh --reset
```

Na Windowsu je druga komanda:

```powershell
.\test.ps1 -Reset
```

Nemoj odmah koristiti `--clean` / `-Clean`. Ta opcija briše namespace i podatke, pa Kubernetes mora ponovo da pravi sve resurse.

## Dijagnostika za 60 sekundi

Pokreni redom:

```bash
docker info
kubectl config current-context
kubectl get nodes
kubectl get pods,jobs,cronjobs -n iep
kubectl get events -n iep --sort-by=.lastTimestamp
```

Zatim za problematični pod:

```bash
kubectl logs IME_PODA -n iep --tail=100
kubectl logs IME_PODA -n iep --previous --tail=100
kubectl describe pod IME_PODA -n iep
```

Pravilo:

- `logs` pokazuje grešku aplikacije;
- `logs --previous` pokazuje prethodni proces kod `CrashLoopBackOff`;
- `describe` i njegov odeljak `Events` pokazuju image, scheduling, volume i probe probleme.

## Značenje najčešćih statusa

| Status | Značenje | Prvi potez |
|---|---|---|
| `Running 1/1` | pod radi i spreman je | ništa |
| `Running 0/1` | proces radi, readiness provera još pada | sačekaj, pa pogledaj log |
| `Completed 0/1` | Job je uspešno završio | ništa — ovo je očekivano |
| `Pending` | pod još nije raspoređen ili čeka volume | `kubectl describe pod ...` |
| `ContainerCreating` | image/volume/network se priprema | sačekaj; ako traje, `describe` |
| `ImagePullBackOff` | image nije dostupan node-u | proveri odeljak o image-ima |
| `CrashLoopBackOff` | proces se pokrene, padne i ponavlja | `logs --previous` |
| `Error` | Job ili proces je izašao sa greškom | `kubectl logs ...` |
| `Terminating` | resurs se gasi | kratko sačekaj; ne pokreći novu seriju komandi |

`kubectl get pods -w` prikazuje svaku promenu statusa. Zato isti contract-checker vidiš više puta: `Pending → ContainerCreating → Running → Completed`. To nisu četiri izvršavanja.

## 1. Nalaziš se u pogrešnom direktorijumu

Simptomi:

- `./start.sh: No such file or directory`;
- pokrenuo si stari projekat;
- podovi koriste neočekivani kod.

Provera:

```bash
pwd
ls
```

Na Windowsu:

```powershell
Get-Location
Get-ChildItem
```

U korenu moraju postojati `Dockerfile`, `k8s`, `services`, `setup`, `start` i `test` skripte. Tek onda pokreni komandu.

## 2. Docker Desktop nije pokrenut

Simptomi:

- `Cannot connect to the Docker daemon`;
- `permission denied ... docker.sock`;
- `docker info` ne uspeva.

Rešenje:

1. Otvori Docker Desktop.
2. Sačekaj da status bude **Running**.
3. Ponovi `docker info`.
4. Tek onda pokreni `start`.

Na Windowsu Docker Desktop mora koristiti **Linux containers**, ne Windows containers. Provera:

```powershell
docker info --format '{{.OSType}}'
```

Rezultat mora biti `linux`.

## 3. Kubernetes nije spreman ili je pogrešan context

Simptomi:

- `The connection to the server ... was refused`;
- `Unable to connect to the server`;
- `kubectl cluster-info` pada;
- `No resources found`, iako znaš da si pokrenuo aplikaciju.

Provera:

```bash
kubectl config get-contexts
kubectl config current-context
kubectl get nodes
```

Rešenje:

1. U Docker Desktop-u proveri da je Kubernetes uključen.
2. Izaberi Docker Desktop Kubernetes context, obično:

```bash
kubectl config use-context docker-desktop
```

3. Sačekaj da `kubectl get nodes` pokaže node `Ready`.

Ne menjaj Kubernetes verziju ili broj node-ova neposredno pred odbranu — Docker Desktop upozorava da to resetuje klaster i briše resurse.

## 4. Aplikacioni image nedostaje — `ImagePullBackOff`

Za `iep-auth`, `iep-employee`, `iep-director` ili `iep-checker` prvo proveri:

```bash
docker image inspect iep-auth:latest
docker image inspect iep-employee:latest
docker image inspect iep-director:latest
docker image inspect iep-checker:latest
```

Ako imaš izvorni kod i bazni `python:3.11-slim` image, aplikacione image-e možeš ponovo napraviti i bez interneta:

macOS/Linux:

```bash
./start.sh --build
```

Windows:

```powershell
.\start.ps1 -Build
```

Ako Docker image postoji, a Kubernetes i dalje pokušava da ga preuzme:

1. proveri `kubectl describe pod IME -n iep`;
2. proveri da Docker Desktop koristi containerd image store;
3. restartuj samo pogođeni deployment:

```bash
kubectl rollout restart deployment/auth -n iep
kubectl rollout restart deployment/employee -n iep
kubectl rollout restart deployment/director -n iep
```

Nemoj menjati `imagePullPolicy: IfNotPresent` u `Always`, jer bi tada lokalni image mogao nepotrebno tražiti registry.

Ako nedostaje infrastrukturni image (`mysql`, `mongo`, `redis` ili `ganache`) i nema interneta, novi klaster ga ne može sam preuzeti. Zato ih `setup` preuzima unapred i zato ne treba resetovati Docker Desktop.

## 5. Kod je izmenjen, ali pod i dalje izvršava staru verziju

Običan `start` namerno ponovo koristi postojeće image-e. Posle izmene Python ili Solidity/artifact koda koristi:

```bash
./start.sh --build
```

Windows:

```powershell
.\start.ps1 -Build
```

Skripta ponovo gradi image-e i restartuje aplikacione deployment-e.

## 6. `CrashLoopBackOff`

Najpre pronađi tačan pod:

```bash
kubectl get pods -n iep
kubectl logs IME_PODA -n iep --previous --tail=100
kubectl describe pod IME_PODA -n iep
```

Česti uzroci:

- auth ne može da pristupi MySQL-u;
- employee ne može da pristupi MongoDB-u ili Redis-u;
- director ne može da pristupi MongoDB-u, Redis-u ili Ganache-u;
- pogrešna ConfigMap/Secret vrednost;
- image sadrži star kod.

Proveri zavisnosti:

```bash
kubectl get pod mysql-0 mongo-0 -n iep
kubectl get pod -l app=redis -n iep
kubectl get pod -l app=ganache -n iep
```

Kada zavisnosti postanu `Ready`, restartuj samo pogođeni servis:

```bash
kubectl rollout restart deployment/auth -n iep
kubectl rollout restart deployment/employee -n iep
kubectl rollout restart deployment/director -n iep
```

## 7. SQL Job ispisuje `Connection refused`

Na početku je normalno da `sql-init` nekoliko puta ispiše:

```text
Database unavailable (...): Can't connect to MySQL ... Connection refused
```

Job ima retry petlju jer MySQL-u treba vremena da se podigne. Ako se log na kraju završava sa:

```text
SQL database initialized successfully.
```

sve je u redu.

Provera:

```bash
kubectl logs job/sql-init -n iep
kubectl get job sql-init -n iep
```

Ako je Job stvarno `Failed`, proveri MySQL:

```bash
kubectl get pod mysql-0 -n iep
kubectl logs mysql-0 -n iep --tail=100
```

Kada je MySQL spreman, ponovi samo Job:

```bash
kubectl delete job sql-init -n iep --ignore-not-found
kubectl apply -f k8s/all.yaml
kubectl wait --for=condition=complete job/sql-init -n iep --timeout=300s
```

Brisanje `sql-init` Job-a ne briše MySQL podatke. Inicijalizacija je idempotentna: postojeći direktor se ne duplira.

## 8. `field is immutable` pri primeni manifesta

Ovo se najčešće odnosi na već postojeći Job čiji je template izmenjen. Rešenje:

```bash
kubectl delete job sql-init -n iep --ignore-not-found
kubectl apply -f k8s/all.yaml
```

Ne moraš zbog jednog Job-a brisati ceo namespace.

## 9. Contract checker se pojavljuje svake minute

To je ispravno ponašanje CronJob-a. Svakog minuta nastaje novi kratkotrajni Job/pod, proveri ugovore i završi kao `Completed`.

Provera rasporeda i poslednjih izvršavanja:

```bash
kubectl get cronjob,jobs -n iep
kubectl logs -l app=contract-checker -n iep --tail=100
```

Ako ne želiš da čekaš sledeći minut, ručno pokreni jednu proveru:

```bash
kubectl delete job contract-checker-manual -n iep --ignore-not-found
kubectl create job --from=cronjob/contract-checker contract-checker-manual -n iep
kubectl wait --for=condition=complete job/contract-checker-manual -n iep --timeout=120s
kubectl logs job/contract-checker-manual -n iep
```

Rezultat `{"processed_contracts": 0}` znači da trenutno nema završenog glasanja za obradu; nije greška.

## 10. Glasanje je završeno, ali MongoDB još nije ažuriran

CronJob radi jednom u minuti, pa prvo sačekaj do 60 sekundi. Ako želiš odmah, pokreni ručni Job iz prethodnog odeljka.

Ako i dalje nema promene:

```bash
kubectl logs job/contract-checker-manual -n iep
kubectl logs deployment/director -n iep --tail=100
kubectl get pod -l app=ganache -n iep
```

Ako je Ganache restartovan dok je glasanje trajalo, ugovor iz Redis-a više ne postoji na novom blockchainu. Za čisto testiranje koristi `test --reset`, koji zajedno čisti Redis/Mongo/MySQL testne podatke i restartuje Ganache.

## 11. Profesorovi testovi ne mogu da se povežu na portove

Skripta automatski otvara port-forward za:

- auth `5000`;
- employee `5001`;
- director `5002`;
- Ganache `8545`.

Ako dobiješ `Connection refused`, proveri servise:

```bash
kubectl get services -n iep
kubectl get pods -n iep
```

Možeš ručno otvoriti četiri terminala:

```bash
kubectl port-forward service/auth 5000:5000 -n iep
kubectl port-forward service/employee 5001:5001 -n iep
kubectl port-forward service/director 5002:5002 -n iep
kubectl port-forward service/ganache 8545:8545 -n iep
```

Svaka komanda ostaje aktivna u svom terminalu. Posle toga u petom terminalu pokreni testove bez gašenja port-forward terminala.

## 12. Port 5000, 5001, 5002 ili 8545 je zauzet

Ovo je posebno nezgodno ako port drži drugi program: test skripta vidi otvoren port i može poslati testove pogrešnoj aplikaciji.

macOS/Linux provera:

```bash
lsof -nP -iTCP:5000 -sTCP:LISTEN
lsof -nP -iTCP:5001 -sTCP:LISTEN
lsof -nP -iTCP:5002 -sTCP:LISTEN
lsof -nP -iTCP:8545 -sTCP:LISTEN
```

Windows PowerShell provera:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 5000,5001,5002,8545
```

Ako je to stari `kubectl port-forward`, zatvori terminal u kojem radi ili zaustavi baš taj PID. Nemoj gasiti nasumične procese. Zatim ponovo pokreni `test --reset`.

## 13. Profesorovi testovi padaju zbog starih podataka

Simptomi su duplikat emaila, neočekivani broj naloga/imovine ili blockchain adresa koja više ne postoji.

Koristi:

```bash
./test.sh --reset
```

Windows:

```powershell
.\test.ps1 -Reset
```

`--reset` ne ruši klaster. Briše samo podatke prethodnog testiranja iz MongoDB/Redis-a, zadržava početnog direktora u MySQL-u i restartuje Ganache.

## 14. Venv ili Python zavisnosti ne rade

Za profesorove testove koristi se poseban venv:

```text
professor_tests/iep_grader/.venv
```

Nemoj ručno pokretati globalni `pytest`; koristi `test.sh` ili `test.ps1`.

Greška `No module named pkg_resources` rešava se ovako:

macOS/Linux:

```bash
professor_tests/iep_grader/.venv/bin/python -m pip install setuptools==70.3.0
```

Windows:

```powershell
professor_tests\iep_grader\.venv\Scripts\python.exe -m pip install setuptools==70.3.0
```

Za ovu instalaciju može biti potreban internet ako paket nije u lokalnom pip cache-u.

Ako je venv kopiran sa drugog operativnog sistema, on nije prenosiv. Obriši samo grader venv i, dok imaš internet, ponovo pokreni `setup`.

macOS/Linux:

```bash
rm -rf professor_tests/iep_grader/.venv
./setup.sh
```

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force professor_tests\iep_grader\.venv
.\setup.ps1
```

Aktivan `(.venv)` u promptu nije greška. To samo znači da terminal trenutno koristi Python virtuelno okruženje; Docker i `kubectl` rade nezavisno od njega.

## 15. PowerShell ne dozvoljava pokretanje skripte

Greška obično kaže da je izvršavanje skripti onemogućeno. Dozvoli ga samo za trenutni terminal:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Zatim ponovi `.\start.ps1` ili `.\test.ps1`. Ovo ne menja trajno sistemsku politiku.

Na macOS/Linux, ako skripta nema execute dozvolu:

```bash
chmod +x setup.sh start.sh test.sh scripts/*.sh
```

## 16. Test je prekinut i ostao je privremeni grader checker

Test skripta ga normalno briše automatski. Ako je terminal nasilno ugašen, proveri:

```bash
kubectl get deployment professor-grader-checker -n iep
```

Ako postoji, ukloni samo pomoćni deployment:

```bash
kubectl delete -f scripts/professor_grader_checker.yaml --ignore-not-found
```

On nije deo obaveznog `k8s/all.yaml` manifesta; služi samo da profesorovi testovi ne čekaju minut na CronJob.

## 17. Pod je `Pending` ili PVC ne može da se veže

Provera:

```bash
kubectl describe pod IME_PODA -n iep
kubectl get pvc -n iep
kubectl get events -n iep --sort-by=.lastTimestamp
```

Česti uzroci su nedovoljno memorije/diska ili problem sa Docker Desktop storage-om. Oslobodi disk, povećaj Docker Desktop resurse ako je moguće i restartuj samo Docker Desktop. Posle povratka proveri `kubectl get nodes` i sačekaj da node bude `Ready`.

Brisanje PVC-a briše podatke. Nemoj to raditi usred odbrane osim ako svesno želiš potpuno čist početak preko `start --clean`.

## 18. Potpuno čisto ponovno pokretanje — poslednja opcija

Koristi samo ako je namespace ozbiljno pokvaren i imaš sve image-e lokalno.

macOS/Linux:

```bash
./start.sh --clean
./test.sh --reset
```

Windows:

```powershell
.\start.ps1 -Clean
.\test.ps1 -Reset
```

`--clean` / `-Clean` briše ceo `iep` namespace, uključujući MySQL i MongoDB PVC podatke, pa sve pravi ispočetka. Ne briše Docker image-e.

Ako nemaš lokalne infrastrukturne image-e i nema interneta, nemoj koristiti ovu opciju.

## Rezervna kopija Docker image-a

Za dodatnu sigurnost, dok je sve ispravno, možeš napraviti veliki arhivski fajl sa svim image-ima aplikacije i infrastrukture:

```bash
docker save -o iep-odbrana-images.tar iep-auth:latest iep-employee:latest iep-director:latest iep-checker:latest python:3.11-slim mysql:8.0.36 mongo:7.0.12 redis:7.2.5-alpine trufflesuite/ganache-cli:v6.12.2
```

Ako image nestane, vraća se sa:

```bash
docker load -i iep-odbrana-images.tar
```

Ove komande rade u terminalu i PowerShell-u. Arhiva može biti velika, pa proveri da ima dovoljno slobodnog prostora.

## Komande koje je najbolje zapamtiti

```bash
kubectl get pods -n iep
kubectl logs IME_PODA -n iep --previous --tail=100
kubectl describe pod IME_PODA -n iep
kubectl get events -n iep --sort-by=.lastTimestamp
kubectl rollout restart deployment/IME -n iep
kubectl logs job/sql-init -n iep
kubectl get cronjob,jobs -n iep
```

Najvažnije pravilo: prvo pročitaj log i `Events`, pa popravljaj samo komponentu koja je pokvarena. Brisanje celog klastera je poslednja, ne prva opcija.

Za moguću modifikaciju „svakog minuta ispiši Redis podatke koje koristi direktor” koristi spreman primer iz [MODIFIKACIJA_REDIS_LOGGER.md](MODIFIKACIJA_REDIS_LOGGER.md).
