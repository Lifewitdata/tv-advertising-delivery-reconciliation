// Optional investigation workbook authoring with @oai/artifact-tool.
// This is an analyst review table, not a BI dashboard.
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const [input,outputDir]=process.argv.slice(2);
if(!input||!outputDir)throw new Error('Usage: build_excel.mjs EXCEL_INPUT_JSON ABSOLUTE_OUTPUT_DIRECTORY');
const data=JSON.parse(await fs.readFile(input,'utf8'));
const wb=Workbook.create();
const review=wb.worksheets.add('Billing review');
const source=wb.worksheets.add('Source');
const advertisers=wb.worksheets.add('Advertisers');
const count=data.review.length,n=count+10,ns=count+4,na=data.advertisers.length+4;
function setup(sheet,lastRow,lastColumn){
  sheet.showGridLines=false;
  sheet.getRange(`A1:${lastColumn}${lastRow}`).format.font={name:'Arial',size:10,color:'#1D2939'};
  sheet.getRange(`A1:${lastColumn}${lastRow}`).format.columnWidth=16;
  sheet.getRange(`A1:${lastColumn}${lastRow}`).format.rowHeight=21;
}
function header(sheet,address){sheet.getRange(address).format={fill:'#243B55',font:{name:'Arial',size:10,color:'#FFFFFF',bold:true},rowHeight:25};}
setup(review,n,'L');setup(source,ns,'H');setup(advertisers,na,'D');
review.getRange('A2').values=[['TV advertising billing investigation']];
review.getRange('A2').format.font={size:15,bold:true};
review.getRange('A3').values=[[`Synthetic snapshot. Cutoff ${data.as_of}. Amounts in USD.`]];
review.getRange('A5').values=[['Open overbilling (USD)']];
review.getRange('D5').values=[['Open shortfall (USD)']];
review.getRange('G5').values=[['Open commitments']];
review.getRange('A6').formulas=[[`=SUMIFS(H11:H${n},I11:I${n},"Overbilled",K11:K${n},"Open")`]];
review.getRange('D6').formulas=[[`=-SUMIFS(H11:H${n},I11:I${n},"Shortfall",K11:K${n},"Open")`]];
review.getRange('G6').formulas=[[`=COUNTIFS(K11:K${n},"Open")`]];
review.getRange('A6').setNumberFormat('$#,##0.00');review.getRange('D6').setNumberFormat('$#,##0.00');
review.getRange('A8').values=[['Update yellow review fields. Source amounts remain the original snapshot.']];
review.getRange('A10:L10').values=[['Commitment','Advertiser','Campaign','Expected USD','Gross USD','Credits USD','Net USD','Difference USD','Direction','Owner','Status','Notes']];
header(review,'A10:L10');
source.getRange('A2').values=[['Commitment billing source']];source.getRange('A2').format.font={size:15,bold:true};
source.getRange('A3').values=[['Source: reconciled commitment fact, synthetic generation run. All money fields below are USD cents.']];
source.getRange('A4:H4').values=[['Commitment','Advertiser ID','Campaign ID','Expected cents','Gross cents','Credit cents','Net cents','Difference cents']];
header(source,'A4:H4');
source.getRange(`A5:H${ns}`).values=data.review.map(r=>[r.commitment_id,r.advertiser_id,r.campaign_id,r.expected_billable_cents,
  r.gross_invoiced_cents,r.credited_cents,r.net_invoiced_cents,r.billing_difference_cents]);
source.getRange(`D5:H${ns}`).setNumberFormat('#,##0');
advertisers.getRange('A2').values=[['Advertiser lookup']];advertisers.getRange('A2').format.font={size:15,bold:true};
advertisers.getRange('A3').values=[['Source: synthetic advertiser dimension.']];
advertisers.getRange('A4:B4').values=[['Advertiser ID','Advertiser']];header(advertisers,'A4:B4');
advertisers.getRange(`A5:B${na}`).values=data.advertisers.map(a=>[a.advertiser_id,a.advertiser_name]);
const formulas=data.review.map((r,i)=>{
  const row=i+11,s=i+5;
  return [`=Source!A${s}`,`=IFNA(VLOOKUP(Source!B${s},Advertisers!$A$5:$B$${na},2,FALSE),"Missing advertiser")`,
    `=Source!C${s}`,`=Source!D${s}/100`,`=Source!E${s}/100`,`=Source!F${s}/100`,`=Source!G${s}/100`,
    `=G${row}-D${row}`,`=IF(H${row}>0,"Overbilled","Shortfall")`];
});
review.getRange(`A11:I${n}`).formulas=formulas;
review.getRange(`K11:K${n}`).values=data.review.map(()=>['Open']);
review.getRange(`J11:L${n}`).format.fill='#FFF2CC';
review.getRange(`K11:K${n}`).dataValidation={rule:{type:'list',values:['Open','Investigating','Resolved']}};
review.getRange(`D11:H${n}`).setNumberFormat('$#,##0.00;($#,##0.00)');
review.getRange('D:H').format.columnWidth=18;review.getRange('I:I').format.columnWidth=20;
review.getRange('B:B').format.columnWidth=33;review.getRange('A:A').format.columnWidth=27;
review.getRange('L:L').format.columnWidth=38;source.getRange('A:A').format.columnWidth=22;
advertisers.getRange('B:B').format.columnWidth=38;
review.tables.add(`A10:L${n}`,true,'BillingInvestigation');
source.tables.add(`A4:H${ns}`,true,'BillingSource');
review.freezePanes.freezeRows(10);source.freezePanes.freezeRows(4);
wb.recalculate();
const expectedOver=data.review.reduce((s,r)=>s+Math.max(r.billing_difference_cents,0)/100,0);
const expectedUnder=data.review.reduce((s,r)=>s+Math.max(-r.billing_difference_cents,0)/100,0);
assert(Math.abs(review.getRange('A6').values[0][0]-expectedOver)<0.001);
assert(Math.abs(review.getRange('D6').values[0][0]-expectedUnder)<0.001);
assert.equal(review.getRange('G6').values[0][0],count);
// A review-status change changes the queue count, without changing ledger data.
review.getRange('K11').values=[['Resolved']];wb.recalculate();
assert.equal(review.getRange('G6').values[0][0],count-1);
review.getRange('K11').values=[['Open']];wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'Billing review!A5:I6',include:'values,formulas',tableMaxRows:2,tableMaxCols:9})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#SPILL!',options:{useRegex:true,maxResults:20},summary:'Formula error scan'})).ndjson);
await fs.mkdir(outputDir,{recursive:true});
for(const sheetName of ['Billing review','Source','Advertisers']){
  const range=sheetName==='Billing review'?'A1:L16':sheetName==='Source'?'A1:H12':'A1:D12';
  const preview=await wb.render({sheetName,range,scale:1.5,format:'png'});
  await fs.writeFile(`${outputDir}/${sheetName.replaceAll(' ','_')}.png`,new Uint8Array(await preview.arrayBuffer()));
}
const workbook=await SpreadsheetFile.exportXlsx(wb);
await workbook.save(`${outputDir}/billing_investigation.xlsx`);
