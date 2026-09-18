# Modifikacija na odbrani — Redis logger svakog minuta

## Šta zapravo treba napraviti

Za zadatak „dodaj pod koji svakog minuta ispisuje direktorove podatke iz Redis-a” odgovarajuća Kubernetes komponenta je **CronJob**. CronJob svakog minuta kreira Job, Job kreira Pod, Pod ispiše podatke i uspešno se završi kao `Completed`.

Nemoj praviti običan Pod sa beskonačnom `while` petljom osim ako profesor izričito zahteva stalno aktivan proces.

U ovom projektu ne postoji ključ `director_messages`. Direktor koristi:

- `pending_orders` — Redis Sorted Set sa UUID-evima naloga;
- `order:<uuid>` — JSON konkretnog BUY/SELL naloga;
- `active_votes` — Redis Sorted Set sa UUID-evima aktivnih glasanja;
- `vote:<uuid>` — JSON metapodataka glasanja.

Zato logger treba da ispiše naloge na čekanju i aktivna glasanja.

## Najbrže rešenje bez izmene Python koda

Napravi fajl `k8s/redis-logger.yaml` sa sledećim sadržajem:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: redis-logger
  namespace: iep
spec:
  schedule: "*/1 * * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 1
      template:
        metadata:
          labels:
            app: redis-logger
        spec:
          restartPolicy: OnFailure
          containers:
            - name: redis-logger
              image: redis:7.2.5-alpine
              imagePullPolicy: IfNotPresent
              command: ["/bin/sh", "-c"]
              args:
                - |
                  echo "=== NALOZI NA CEKANJU ==="
                  for uuid in $(redis-cli -h redis ZRANGE pending_orders 0 -1); do
                    echo "order:$uuid"
                    redis-cli -h redis --raw GET "order:$uuid"
                  done

                  echo "=== AKTIVNA GLASANJA ==="
                  for uuid in $(redis-cli -h redis ZRANGE active_votes 0 -1); do
                    echo "vote:$uuid"
                    redis-cli -h redis --raw GET "vote:$uuid"
                  done

                  echo "=== KRAJ ISPISA ==="
```

Zašto koristi `redis:7.2.5-alpine`:

- image već postoji u projektu i pripremljen je preko `setup` skripte;
- sadrži `redis-cli`;
- ne moraš da menjaš Python kod;
- ne moraš ponovo da gradiš `iep-checker` image;
- radi bez interneta ako je image unapred preuzet.

## Pokretanje

```bash
kubectl apply -f k8s/redis-logger.yaml
kubectl get cronjob redis-logger -n iep
```

Cron izraz `*/1 * * * *` znači „svakog minuta”. Prvo automatsko izvršavanje možeš čekati do 60 sekundi.

Prikaži nastale Job-ove i Pod-ove:

```bash
kubectl get jobs,pods -n iep -l app=redis-logger
```

Prikaži logove poslednjih logger Pod-ova:

```bash
kubectl logs -l app=redis-logger -n iep --tail=200
```

## Kako odmah demonstrirati, bez čekanja jednog minuta

Ručno napravi jedan Job iz CronJob šablona:

```bash
kubectl delete job redis-logger-manual -n iep --ignore-not-found
kubectl create job --from=cronjob/redis-logger redis-logger-manual -n iep
kubectl wait --for=condition=complete job/redis-logger-manual -n iep --timeout=120s
kubectl logs job/redis-logger-manual -n iep
```

Ako su Redis liste prazne, videćeš samo naslove i završnu poruku. To znači da logger radi, ali trenutno nema naloga ni aktivnih glasanja.

## Kako proveriti Redis ručno

```bash
kubectl exec deployment/redis -n iep -- redis-cli ZRANGE pending_orders 0 -1
kubectl exec deployment/redis -n iep -- redis-cli ZRANGE active_votes 0 -1
kubectl exec deployment/redis -n iep -- redis-cli KEYS 'order:*'
kubectl exec deployment/redis -n iep -- redis-cli KEYS 'vote:*'
```

Ako dobiješ UUID, konkretan zapis čitaš ovako:

```bash
kubectl exec deployment/redis -n iep -- redis-cli GET order:OVDE_UUID
kubectl exec deployment/redis -n iep -- redis-cli GET vote:OVDE_UUID
```

## Ako profesor bukvalno zahteva `director_messages`

Tada prvo moraš definisati gde se poruke čuvaju. Najjednostavnije je da ih kod koji ih proizvodi dodaje u Redis List:

```python
redis_client.rpush("director_messages", json.dumps(message))
```

CronJob zatim umesto petlji može koristiti:

```yaml
command: ["redis-cli"]
args: ["-h", "redis", "--raw", "LRANGE", "director_messages", "0", "-1"]
```

Važna razlika:

- Redis **List** čuva istoriju i `LRANGE` je može naknadno ispisati;
- Redis **Pub/Sub** ne čuva stare poruke — logger vidi samo poruke dok je aktivno pretplaćen;
- Redis **Stream** čuva istoriju i bolji je za ozbiljniji sistem poruka, ali je za kratku modifikaciju složeniji od Liste.

Ako zadatak kaže „ispiši sve poruke svakog minuta”, List ili Stream imaju smisla; čist Pub/Sub nije dovoljan za istoriju.

## Ako profesor ipak zahteva stalni dodatni Pod

Tada koristi Deployment sa jednom replikom i petljom:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis-logger
  namespace: iep
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis-logger
  template:
    metadata:
      labels:
        app: redis-logger
    spec:
      containers:
        - name: redis-logger
          image: redis:7.2.5-alpine
          imagePullPolicy: IfNotPresent
          command: ["/bin/sh", "-c"]
          args:
            - |
              while true; do
                date
                echo "=== NALOZI NA CEKANJU ==="
                for uuid in $(redis-cli -h redis ZRANGE pending_orders 0 -1); do
                  redis-cli -h redis --raw GET "order:$uuid"
                done
                echo "=== AKTIVNA GLASANJA ==="
                for uuid in $(redis-cli -h redis ZRANGE active_votes 0 -1); do
                  redis-cli -h redis --raw GET "vote:$uuid"
                done
                sleep 60
              done
```

Logovi Deployment varijante:

```bash
kubectl logs deployment/redis-logger -n iep -f
```

Za zahtev „svakog minuta uradi posao” na odbrani prvo predloži CronJob i obrazloži da je to Kubernetes komponenta namenjena periodičnim zadacima. Deployment koristi samo ako profesor insistira da isti Pod stalno ostane `Running`.

## Uklanjanje modifikacije

Za CronJob varijantu:

```bash
kubectl delete -f k8s/redis-logger.yaml --ignore-not-found
kubectl delete job redis-logger-manual -n iep --ignore-not-found
```

Ovo ne dira Redis podatke niti ostatak aplikacije.

