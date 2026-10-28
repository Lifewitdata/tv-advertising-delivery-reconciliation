"""Package complete Tableau-ready data and sources; this creates no BI workbook."""
import zipfile
from tvads.pipeline import current_output


def package():
    out=current_output()
    target=out/'tv_advertising_verified_data.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for folder in ['raw','oracles','reports','tableau_ready']:
            for path in sorted((out/folder).glob('*')):
                if path.is_file():archive.write(path,str(path.relative_to(out)))
        archive.write(out/'run_manifest.json','run_manifest.json')
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert 'tableau_ready/fact_commitment_delivery_billing.csv' in archive.namelist()
    print(target)
    return target


if __name__=='__main__':package()
