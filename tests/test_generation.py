import tempfile
from pathlib import Path
from app.services.generator import certificate_generator


def test_certificate_generator_basic():
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = Path(tmp_dir) / "cert.pdf"
        certificate_generator.generate(
            output_path=pdf_path,
            recipient_name="Marie Curie",
            event_name="Nobel Physics Lecture",
            issuer_name="Royal Academy of Sciences",
            issue_date="2026-10-08",
            certificate_id="CERT-TEST-1234-5678",
            description="For distinguished contributions in radioactivity research.",
            extra_data={"grade": "Distinction", "honors": "First Class"},
            template_type="classic"
        )

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 1000

        with open(pdf_path, "rb") as f:
            header = f.read(5)
            assert header == b"%PDF-"


def test_certificate_generator_hindi_devanagari_unicode():
    """
    Ensures that Hindi (Devanagari) names render into the PDF without
    UnicodeEncodeError or character rendering crashes.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = Path(tmp_dir) / "cert_hindi.pdf"
        hindi_name = "राहुल शर्मा (Rahul Sharma)"
        hindi_event = "आर्टिफिशियल इंटेलिजेंस और मशीन लर्निंग (AI & Machine Learning)"

        certificate_generator.generate(
            output_path=pdf_path,
            recipient_name=hindi_name,
            event_name=hindi_event,
            issuer_name="भारतीय प्रौद्योगिकी संस्थान (IIT)",
            issue_date="2026-10-08",
            certificate_id="CERT-HNDI-8899-0011",
            description="उत्कृष्ट प्रदर्शन और पूर्णता प्रमाण पत्र",
            template_type="classic"
        )

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 2000

        with open(pdf_path, "rb") as f:
            assert f.read(5) == b"%PDF-"


def test_certificate_generator_modern_template():
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = Path(tmp_dir) / "cert_modern.pdf"
        certificate_generator.generate(
            output_path=pdf_path,
            recipient_name="Grace Hopper",
            event_name="Compiler Architecture Summit",
            issuer_name="Computing Heritage",
            issue_date="2026-10-08",
            certificate_id="CERT-MODN-4455-6677",
            template_type="modern"
        )

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 1000

        with open(pdf_path, "rb") as f:
            assert f.read(5) == b"%PDF-"


def test_certificate_generator_long_strings():
    """Ensure font scaling works and does not throw exception for very long names."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = Path(tmp_dir) / "cert_long.pdf"
        long_name = "His Imperial Majesty Emperor Maximilian Alexander Bartholomew Montgomery III of Hohenzollern-Sigmaringen"
        long_event = "Advanced Comprehensive Postgraduate Diploma in Applied Quantum Neural Computing and Distributed Supercomputing Systems"

        certificate_generator.generate(
            output_path=pdf_path,
            recipient_name=long_name,
            event_name=long_event,
            issuer_name="International Consortium of Advanced Computational Studies",
            issue_date="2026-10-08",
            certificate_id="CERT-LONG-1122-3344",
        )

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 1000
