"""PMMP detail structured parsing — estimate vs caution safety."""
from datetime import timedelta
from unittest.mock import Mock

from backend.app.core.validation import today_in_morocco
from backend.app.integrations.http.html import Page
from backend.app.integrations.pmmp.parser import (
    enrich_detail, procurement_metadata, build_pmmp_detail, labelled_fields)
from test_agent import candidate
from test_phase3 import URL


def full_notice(extra=''):
    deadline = (today_in_morocco() + timedelta(days=20)).strftime('%d/%m/%Y')
    published = today_in_morocco().strftime('%d/%m/%Y')
    return Page(
        f'<h1>Études et suivi — ancienne médina</h1>'
        f'<p>Référence : REF-GUEL-1</p>'
        f'<p>Objet : REALISATION DES ETUDES ET SUIVI DES TRAVAUX DE REHABILITATION '
        f'DE L’ANCIENNE MEDINA DE LA VILLE DE GUELMIM</p>'
        f'<p>Acheteur public : Commune de Guelmim</p>'
        f'<p>Type d’annonce : Avis d’appel d’offres ouvert</p>'
        f'<p>Procédure : Appel d’offres ouvert</p>'
        f'<p>Catégorie principale : Prestations intellectuelles</p>'
        f'<p>Allotissement : Non alloti</p>'
        f'<p>Lieu d’exécution : Guelmim</p>'
        f'<p>Date de publication : {published}</p>'
        f'<p>Date et heure limite de remise des plis : {deadline} à 10:30</p>'
        f'<p>Estimation du coût des prestations : 3 552 000 MAD TTC</p>'
        f'<p>Caution provisoire : 70 000 MAD</p>'
        f'<p>Réservé aux TPE/PME : Oui</p>'
        f'<p>Domaines d’activité : Architecture ; Patrimoine</p>'
        f'<p>Mode de retrait : Plateforme PMMP</p>'
        f'<p>Mode de dépôt : Dépôt électronique</p>'
        f'<p>Lieu d’ouverture des plis : Siège de la commune</p>'
        f'<p>Prix d’acquisition des plans : 500 MAD</p>'
        f'<p>Qualifications : Architecte / Bureau d’études</p>'
        f'<p>Documents : DCE CPS RC BPU plans annexes</p>{extra}'
    )


def test_estimate_and_caution_never_cross_map():
    facts = procurement_metadata(full_notice(), URL)
    assert facts['estimated_amount'] == 3_552_000
    assert facts['provisional_bond_amount'] == 70_000
    assert facts['estimated_amount'] != facts['provisional_bond_amount']


def test_structured_pmmp_detail_fields():
    page = full_notice()
    facts = {**labelled_fields(page), **procurement_metadata(page, URL)}
    facts['location_evidence'] = facts.pop('location', None)
    facts['deadline_time'] = '10:30'
    facts.setdefault('plan_price_amount', 500)
    facts.setdefault('plan_price_currency', 'MAD')
    pmmp = build_pmmp_detail(facts, URL, page.text)
    assert pmmp['reference']
    assert pmmp['buyer']
    assert pmmp['estimate']['amount'] == 3_552_000
    assert pmmp['provisional_guarantee']['amount'] == 70_000
    assert pmmp['deadline']['time'] == '10:30'
    assert pmmp['sme_reserved'] is True
    assert pmmp['documents']['dce'] is True
    assert pmmp['activity_domains']
    assert pmmp['official_url'] == URL


def test_enrich_detail_stores_pmmp_in_metadata():
    pages = Mock()
    pages.get.return_value = (URL, full_notice())
    item = enrich_detail(candidate(url=URL, official_url=URL, title='Études médina',
                                   reference='REF-GUEL-1', institution='Commune de Guelmim'), pages)
    assert item.estimated_amount == 3_552_000
    assert item.provisional_bond_amount == 70_000
    assert item.metadata['pmmp']['estimate']['amount'] == 3_552_000
    assert item.metadata['pmmp']['provisional_guarantee']['amount'] == 70_000
    assert item.metadata['detail_enrichment_status'] == 'enriched'


def test_missing_estimate_still_parses_other_fields():
    page = Page(
        '<p>Référence : REF-2</p><p>Acheteur public : Ville</p>'
        '<p>Lieu d’exécution : Rabat</p><p>Caution provisoire : 10 000 MAD</p>')
    facts = procurement_metadata(page, URL)
    assert 'estimated_amount' not in facts
    assert facts['provisional_bond_amount'] == 10_000
