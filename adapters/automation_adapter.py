
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, NoSuchElementException
import queue
from typing import Optional, Dict, Any

from automation_library.core.interfaces import BaseAuthenticator, BaseExtractor, BaseInput, Session, TaskItem, DataItem
from typing import Iterable
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, NoSuchElementException, WebDriverException

class AtlasCopcoAuthenticator(BaseAuthenticator):
    def __init__(self, credentials: Dict[str, str], headless: bool = True, log_queue: Optional[queue.Queue] = None):
        self.credentials = credentials
        self.headless = headless
        self.log_queue = log_queue

    def _log(self, message: str):
        if self.log_queue:
            self.log_queue.put(message)
        else:
            print(message)

    def _configure_driver(self) -> webdriver.Chrome:
        options = ChromeOptions()
        options.add_argument('--log-level=3')
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1200,800")
        if self.headless:
            options.add_argument("--headless=new")
        return webdriver.Chrome(options=options)

    def login(self, ready_callback: Optional[callable] = None) -> Session:
        driver = self._configure_driver()
        try:
            # O ScraperWorker já loga a tentativa de login por worker. Se estamos em um contexto
            # com log_queue (UI), suprimimos a mensagem genérica para evitar repetição.
            if not self.log_queue:
                self._log("Iniciando processo de login...")
            driver.get("https://ctshoponline.atlascopco.com/pt-BR/login")
            WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
            WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Conecte-se')]"))).click()
            
            email_input = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, "//input[@type='email']")))
            email_input.send_keys(self.credentials['username'])
            WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, "//input[@type='submit']"))).click()
            
            password_input = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, "//input[@type='password']")))
            password_input.send_keys(self.credentials['password'])
            WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.ID, "idSIButton9"))).click()
            
            WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.ID, "idBtn_Back"))).click()
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, "//p[contains(., 'Welcome')]")))
            self._log("Login bem-sucedido!")
            # Se o callback ready for fornecido, chama-o para indicar que o driver
            # está pronto (o callback pode aceitar o driver ou nenhum parâmetro).
            try:
                if ready_callback:
                    try:
                        ready_callback(driver)
                    except TypeError:
                        # callback sem argumentos
                        ready_callback()
            except Exception:
                pass
            return driver
        except Exception as e:
            self._log(f"❌ Falha no login: {e}")
            if driver:
                driver.quit()
            raise

    def logout(self, session: Session):
        if session:
            try:
                session.quit()
            except Exception:
                pass

class AtlasCopcoExtractor(BaseExtractor):
    def __init__(self, log_queue: Optional[queue.Queue] = None):
        self.log_queue = log_queue

    def _log(self, message: str):
        if self.log_queue:
            self.log_queue.put(message)
        else:
            print(message)

    def extract(self, session: Session, task_item: TaskItem) -> DataItem:
        driver = session
        product_code, row_num = task_item['code'], task_item['row_num']
        worker_id = task_item.get('worker_id', 'N/A')
        log_prefix = f"[Worker {worker_id}] " if worker_id != 'N/A' else ""
        log_line = f"linha {row_num}: " if row_num else ""

        def _log(msg: str):
            self._log(f"{log_prefix}{log_line}{msg}")

        try:
            driver.get(f"https://ctshoponline.atlascopco.com/en-GB/products/{product_code}")
            _log(f"Acessando: {product_code}")
            
            locators = {
                "product_name": (By.XPATH, "//*[@id='__next']/div/div/div[1]/div[2]/section/div/div[1]/h1"),
                "not_found": (By.XPATH, "//h2[contains(., 'The server cannot find the requested resource.') ]"),
                "no_longer_available": (By.XPATH, "//*[contains(text(), 'The product is no longer available') ]"),
                "cannot_add": (By.XPATH, "//h5[contains(., 'Product cannot be added to cart')]"),
            }

            try:
                element = WebDriverWait(driver, 10).until(
                    EC.any_of(
                        EC.presence_of_element_located(locators["product_name"]),
                        EC.presence_of_element_located(locators["not_found"])
                    )
                )
            except TimeoutException:
                _log(f"❌ Timeout: {product_code}")
                return {"code": product_code, "name": "", "status": "Tempo Esgotado", "row_num": row_num}

            if element.tag_name == 'h2':
                _log(f"❌ Não encontrado: {product_code}")
                return {"code": product_code, "name": "", "status": "Não Encontrado", "row_num": row_num}

            # Inicializa produto com todos os campos esperados
            product = {
                "code": product_code,
                "name": element.text,
                "status": "Disponível",
                "row_num": row_num,
                "pricing": "",
                "discount": "",
                "pricing_with": "",
                "cofins_tax": "",
                "cofins_value": "",
                "difalst_tax": "",
                "difalst_value": "",
                "fecop_tax": "",
                "fecop_value": "",
                "icmi_value": "",
                "icms_tax": "",
                "icms_value": "",
                "ipi_tax": "",
                "ipi_value": "",
                "pis_tax": "",
                "pis_value": "",
                "st_tax": "",
                "st_value": "",
                "weight": "",
                "country_of_origin": "",
                "customs_tariff": "",
                "possibility_to_return": ""
            }

            # SEÇÃO 1: PREÇOS
            try:
                pricing_tab = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Pricing')]") )
                )
                driver.execute_script("arguments[0].click();", pricing_tab)
                xpath_com_condicao = "(//div[@role='tabpanel']//td)[1][contains(., 'BRL') or contains(., 'R$')]"
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, xpath_com_condicao))
                ).text
                tds = [td.text for td in driver.find_elements(By.XPATH, "//div[@role='tabpanel']//td")]

                if len(tds) >= 1:
                    product["pricing"] = tds[0].replace("R$", "").replace("BRL ", "")
                if len(tds) >= 2:
                    product["discount"] = "0" if tds[1] == "-" else tds[1]
                if len(tds) >= 3:
                    product["pricing_with"] = tds[2].replace("R$", "").replace("BRL ", "")

            except Exception as e:
                # verifica indisponibilidade
                if driver.find_elements(*locators["no_longer_available"]) or driver.find_elements(*locators["cannot_add"]):
                    _log(f"⚠️ Produto indisponível: {product_code}")
                    product["status"] = "Indisponível"
                    _log(f"✅ Sucesso (Indisponível): {product_code}")
                    return product
                else:
                    _log(f"⚠️ Erro preços: {str(e)}")

            # SEÇÃO 2: IMPOSTOS
            try:
                taxes_tab = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Taxes')]") )
                )
                driver.execute_script("arguments[0].click();", taxes_tab)
                table = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//div[@role='tabpanel']//table"))
                )
                cells = [cell.text for cell in driver.find_elements(By.XPATH, "//div[@role='tabpanel']//td[@data-cy='informationTableCell']")]

                def _parse_tax(tax_str):
                    if not tax_str:
                        return "", ""
                    if "% (BRL " in tax_str:
                        parts = tax_str.split("% (BRL ")
                        return parts[0], parts[1].replace(")", "")
                    elif "BRL " in tax_str:
                        return "", tax_str.split("BRL ")[1]
                    return "", tax_str

                tax_fields = [
                    ("cofins", 1), ("difalst", 3), ("fecop", 5),
                    ("icms", 9), ("ipi", 11), ("pis", 13), ("st", 15)
                ]

                for field, index in tax_fields:
                    if len(cells) > index:
                        tax, value = _parse_tax(cells[index])
                        product[f"{field}_tax"] = tax
                        product[f"{field}_value"] = value

            except Exception as e:
                _log(f"⚠️ Erro impostos: {str(e)}")

            # SEÇÃO 3: INFORMAÇÕES DO PRODUTO
            try:
                info_tab = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Product information')]") )
                )
                driver.execute_script("arguments[0].click();", info_tab)
                table = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//div[@role='tabpanel']//table"))
                )

                for tr in table.find_elements(By.TAG_NAME, "tr"):
                    tds = tr.find_elements(By.TAG_NAME, "td")
                    if len(tds) < 2:
                        continue
                    key = tds[0].text.strip().lower()
                    value = tds[1].text.strip()
                    if "country of origin" in key:
                        product["country_of_origin"] = value
                    elif "customs tariff" in key:
                        product["customs_tariff"] = value
                    elif "weight" in key:
                        product["weight"] = value
                    elif "possibility to return" in key:
                        product["possibility_to_return"] = value

            except Exception as e:
                _log(f"⚠️ Erro informações: {str(e)}")

            _log(f"✅ Sucesso: {product_code}")
            return product

        except Exception as e:
            _log(f"❌ ERRO GRAVE: {str(e)}")
            return {"code": product_code, "name": "", "status": f"ERRO GRAVE: {str(e)}", "row_num": row_num}


class AtlasCopcoInput(BaseInput):
    """Placeholder BaseInput para o adaptador AtlasCopco.

    Esta classe serve como ponto de integração entre o adaptador específico
    (que contém o extractor e o authenticator) e os provedores genéricos do
    framework. Implementações concretas (ExcelInput, CSVInput, DBInput, etc.)
    devem herdar desta classe e implementar `open`, `get_items` e `close`.

    Atributos padrões:
    - uses_file: indica se o input depende de um arquivo (ex: Excel/CSV).
    """

    uses_file: bool = False

    def open(self):
        raise NotImplementedError("AtlasCopcoInput.open() must be implemented by a concrete input provider")

    def get_items(self) -> Iterable[TaskItem]:
        raise NotImplementedError("AtlasCopcoInput.get_items() must be implemented by a concrete input provider")

    def close(self):
        raise NotImplementedError("AtlasCopcoInput.close() must be implemented by a concrete input provider")


# Exponha o input padrão (placeholder) e a chave identificadora usada pelo
# extractor. Isso permite que a UI ou pipeline monte automaticamente o
# provedor de entrada e saiba qual campo do TaskItem contém o identificador
# a ser pesquisado.
input_class = AtlasCopcoInput
# Nome da chave no TaskItem que contém o identificador pesquisado pelo extractor
input_id_key = "code"
