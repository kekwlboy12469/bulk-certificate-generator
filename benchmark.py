import time
import tempfile
from pathlib import Path
from app.services.generator import certificate_generator


def run_benchmark(n_certificates: int = 100):
    print(f"=== Running Dual Certificate Generation Benchmark ({n_certificates} certs each) ===")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # --- 1. Latin Benchmark ---
        latin_sizes = []
        start_latin = time.perf_counter()
        for i in range(1, n_certificates + 1):
            cert_id = f"CERT-LATN-{i:04d}"
            output_file = tmp_path / f"cert_latin_{i:04d}.pdf"
            certificate_generator.generate(
                output_path=output_file,
                recipient_name=f"Standard Recipient #{i:03d}",
                event_name="High-Performance Systems & Engineering 2026",
                issuer_name="Engineering Benchmarks Council",
                issue_date="2026-10-08",
                certificate_id=cert_id,
                description="For demonstrating exceptional scalability and algorithmic efficiency under load.",
                extra_data={"score": f"{90 + (i % 10)}%", "rank": i},
                template_type="classic" if i % 2 == 0 else "modern"
            )
            latin_sizes.append(output_file.stat().st_size)
        time_latin = time.perf_counter() - start_latin

        # --- 2. Devanagari (Hindi) Benchmark ---
        hindi_sizes = []
        start_hindi = time.perf_counter()
        for i in range(1, n_certificates + 1):
            cert_id = f"CERT-HNDI-{i:04d}"
            output_file = tmp_path / f"cert_hindi_{i:04d}.pdf"
            certificate_generator.generate(
                output_path=output_file,
                recipient_name=f"राहुल शर्मा #{i:03d}",
                event_name="क्लाउड और वितरित प्रणाली प्रमाणन (Cloud & Distributed Systems)",
                issuer_name="भारतीय प्रौद्योगिकी परिषद",
                issue_date="2026-10-08",
                certificate_id=cert_id,
                description="सफलतापूर्वक पाठ्यक्रम पूरा करने और उत्कृष्टता प्राप्त करने के उपलक्ष्य में",
                extra_data={"rank": i},
                template_type="classic"
            )
            hindi_sizes.append(output_file.stat().st_size)
        time_hindi = time.perf_counter() - start_hindi

        # Calculations
        latin_avg_ms = (time_latin / n_certificates) * 1000
        latin_throughput = n_certificates / time_latin
        latin_avg_kb = (sum(latin_sizes) / len(latin_sizes)) / 1024

        hindi_avg_ms = (time_hindi / n_certificates) * 1000
        hindi_throughput = n_certificates / time_hindi
        hindi_avg_kb = (sum(hindi_sizes) / len(hindi_sizes)) / 1024

        print("\n--- Benchmark Results ---")
        print(f"1. Standard Latin Template (Type 1 Fonts + Vector QR):")
        print(f"   Execution Time:       {time_latin:.3f} s ({n_certificates} certs)")
        print(f"   Avg Latency per Cert: {latin_avg_ms:.2f} ms")
        print(f"   Throughput:           {latin_throughput:.1f} certs/sec")
        print(f"   Avg File Size:        {latin_avg_kb:.2f} KB\n")

        print(f"2. Devanagari / Hindi Template (Bundled TrueType Font + Vector QR):")
        print(f"   Execution Time:       {time_hindi:.3f} s ({n_certificates} certs)")
        print(f"   Avg Latency per Cert: {hindi_avg_ms:.2f} ms")
        print(f"   Throughput:           {hindi_throughput:.1f} certs/sec")
        print(f"   Avg File Size:        {hindi_avg_kb:.2f} KB")
        print("-------------------------\n")


if __name__ == "__main__":
    run_benchmark(100)
