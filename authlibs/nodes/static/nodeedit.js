function findRows() {
	x = document.getElementById("div_kv_base");
	rows  = x.querySelectorAll(".kvdiv");
	console.log(rows);
	for (var i=0;i<rows.length;i++) {
		kvrow=rows[i];
		kv_id = kvrow.be_kv_id;
		k  = kvrow.querySelector(".kv_input_key");
		v  = kvrow.querySelector(".kv_input_value");
		k_val = k.value
		v_val = v.value
		console.log("KEY",kv_id,k_val,v_val);
	}
}

function ClickDelete(x) {
	findRows();
}

function ClickAdd() {
	alert();
}
