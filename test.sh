#!/bin/bash
# ── NAUTA Lead Agent — Test Suite ──────────────────────────────────────────────

BASE="http://localhost:8000"
SEP="────────────────────────────────────────"

echo ""
echo "$SEP"
echo "1) HIGH ICP — debe enviar email y guardar en DB"
echo "$SEP"
curl -s -X POST $BASE/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "page_visited": "/pricing",
    "person": {
      "first_name": "Sarah",
      "last_name": "Chen",
      "email": "sarah.chen@test-company.com",
      "job_title": "VP Supply Chain",
      "linkedin_url": "https://linkedin.com/in/sarahchen-test",
      "company": {
        "name": "Acme Distribution Co",
        "website": "acmedist.com",
        "industry": "Wholesale Distribution",
        "employee_count": 3500,
        "revenue": "$2.5B",
        "location": "Chicago, IL"
      }
    }
  }'

echo ""
echo ""
echo "$SEP"
echo "2) DUPLICADO — mismo payload, debe devolver duplicate"
echo "$SEP"
curl -s -X POST $BASE/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "page_visited": "/pricing",
    "person": {
      "first_name": "Sarah",
      "last_name": "Chen",
      "email": "sarah.chen@test-company.com",
      "job_title": "VP Supply Chain",
      "linkedin_url": "https://linkedin.com/in/sarahchen-test",
      "company": {
        "name": "Acme Distribution Co",
        "industry": "Wholesale Distribution",
        "employee_count": 3500,
        "revenue": "$2.5B",
        "location": "Chicago, IL"
      }
    }
  }'

echo ""
echo ""
echo "$SEP"
echo "3) POTENTIAL ICP — debe ir a la cola de revisión"
echo "$SEP"
curl -s -X POST $BASE/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "page_visited": "/features",
    "person": {
      "first_name": "James",
      "last_name": "Rivera",
      "email": "j.rivera@midsize-mfg.com",
      "job_title": "Director of Logistics",
      "company": {
        "name": "MidSize Manufacturing",
        "industry": "Manufacturing",
        "employee_count": 600,
        "revenue": "$400M",
        "location": "Dallas, TX"
      }
    }
  }'

echo ""
echo ""
echo "$SEP"
echo "4) QUEUE — leads en pending_review"
echo "$SEP"
curl -s $BASE/queue

echo ""
echo ""
echo "$SEP"
echo "5) APPROVE lead 2 — envía el email guardado"
echo "$SEP"
curl -s -X POST $BASE/leads/2/approve

echo ""
echo ""
echo "$SEP"
echo "6a) EMAIL HISTORY — lead 1 (High ICP)"
echo "$SEP"
curl -s $BASE/leads/1/emails

echo ""
echo ""
echo "$SEP"
echo "6b) EMAIL HISTORY — lead 2 (Potential ICP aprobado)"
echo "$SEP"
curl -s $BASE/leads/2/emails

echo ""
echo ""
echo "$SEP"
echo "7) HEALTH — estado del servidor, DB y scheduler"
echo "$SEP"
curl -s $BASE/health

echo ""
echo ""
