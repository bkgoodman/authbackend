nextKey=0;
function findRows(findRow) {
	rval=null;
	x = document.getElementById("div_kv_base");
	rows  = x.querySelectorAll(".kvdiv");
	console.log(rows);
	for (var i=0;i<rows.length;i++) {
		kvrow=rows[i];
		kv_id = parseInt(kvrow.getAttribute("be_kv_id"));
		if (kv_id >= nextKey)
			nextKey = kv_id+1;
		k  = kvrow.querySelector(".kv_input_key");
		if (k) {
			v  = kvrow.querySelector(".kv_input_value");
			k_val = k.value;
			v_val = v.value;
			if ((findRow != null) && (kv_id == findRow))
				rval = kvrow;
		}
		// console.log("KEY",kv_id,k_val,v_val,kvrow);
	}
	if  (rval) {
		newid= rval.getAttribute("be_kv_id");
		rval.innerHTML="<input type=\"hidden\" id=\"delete_kv_"+String(newid)+"\"  name=\"delete_kv_"+String(newid)+"\" be_kv_id=\""+String(newid)+"\" />";
	}
}


function ClickDelete(x) {
	rt=findRows(x);
	console.log("RETURN DELETE",x,rt);
}
TEMPLATE=`
			<div class="form-row kvdiv" be_kv_id="XXX" id="kv_row_XXX">
				<div class="form-group col-md-4">
					<label>Key:</label>
					<input type="text" class="form-control kv_input_key" name="key_input_XXX" id="key_input_XXX"  value="">
				</div>
				<div class="form-group col-md-4">
					<label>Value:</label>
					<input type="text" class="form-control kv_input_value" name="value_input_XXX" id="value_input_XXX"  value="">
				</div>
				<div class="form-group col-md-1">
					<label>&nbsp;</label>
					<input type="hidden" class="form-control kv_input_value" name="new_input_XXX" id="new_input_XXX"  value="1">
					<img src="IMG_BASEdelete_ico_grey.png" onclick="ClickDelete(XXX);" width="32px" />
				</div>
			</div>
	`;

String.prototype.replaceAll = function(search, replacement) {
    var target = this;
    return target.replace(new RegExp(search, 'g'), replacement);
};

function ClickAdd() {
	findRows(null);
	x = document.getElementById("div_kv_base");
	v = TEMPLATE.replace("IMG_BASE",IMG_BASE).replaceAll("XXX",nextKey);
	x.innerHTML += v;
	nextKey = nextKey+1;
}
